from custom_logging import CustomizeLogger
from fastapi import Security, Depends, HTTPException, status, UploadFile, File, Form, FastAPI, Request,requests
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader, APIKey
from io import BytesIO
from datetime import datetime, timedelta
import json, os, time, requests, threading, logging, pickle, uuid, pytz
from pydantic import BaseModel, validator, HttpUrl, Json
import pandas as pd
from Redis import Cache
from pymongo import MongoClient
from utils import get_prerecorded_encodings

if not os.path.exists('logs'):
    os.makedirs('logs')

#s3 = boto3.client('s3',aws_access_key_id="AKIATHECBORXQEJNS7PS",aws_secret_access_key="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")
client = MongoClient('mongodb://127.0.0.1:27017/?directConnection=true&serverSelectionTimeoutMS=2000&appName=mongosh+1.8.1')
#db_name = f"DATABASE_{campaign_id}"
db = client.DATABASE_AiLife_CCOM04
key_db = client.keydb
key_collection = key_db.keys_database
detail_collection = db.voicebot
queue_collection = db.queue
ongoing_collection = db.ongoing
new_completed_call = db.completed_call


# this is updating the keys which are added for data security between dailer & dashboard
document = {"_id":"keys","dashboard_reference": "cc0e6904-3f3d-4516-95bd-4e6f7db777b2","dialer_reference": "8b5c9c99-fdf3-4b5b-b4ff-bf7aca7f73ef"}

app = FastAPI(title="Voicebot API", debug=True)
logger = logging.getLogger(__name__)
logger = CustomizeLogger.make_logger("logging_config.json")
app.logger = logger

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PARALLEL_CALLS = 60
cache = Cache()
#app.logger.info("Redis Cache Connection Successful...")
api_key_header = APIKeyHeader(name="access_token", auto_error=False)

class VerifyCredentials:
  def __init__(self, API_KEY: str):
    self.API_KEY = API_KEY
  async def __call__(self, api_key_header: str = Security(api_key_header)):
    if api_key_header == self.API_KEY:
      return api_key_header
    else:
      raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Could not validate credentials"
      )

def delete_selected(detail_collection, queue_collection, ongoing_collection):
    detail_collection.delete_many({})
    queue_collection.delete_many({})
    ongoing_collection.delete_many({})

# loading dailer API key as well as dashboard API key
keys_data = key_collection.find_one({"_id": "keys"})
verify_dialer_credentials = VerifyCredentials(keys_data["dialer_reference"])
verify_dashboard_credentials = VerifyCredentials(keys_data["dashboard_reference"])


def isNowInTimeRange(start, end):
    ist = pytz.timezone('Asia/Kolkata')
    start_time = datetime.strptime(start, '%H:%M').time()
    end_time = datetime.strptime(end, '%H:%M').time()
    now_ist = datetime.now(ist).time()
    return start_time <= now_ist <= end_time

def check_date(date_):
    ist = pytz.timezone('Asia/Kolkata')
    new_date = datetime.strptime(date_, '%d/%m/%Y').date()
    current_date = datetime.now(ist).date()
    status = current_date == new_date
    #app.logger.info(f"[{new_date}]  >= {current_date}  |   {status}")
    return status

def clean_up(temp):
    #app.logger.info("Inside Cleanup Function")
    try:
        cache.delete_item(f'DICT_{campaign_id}', temp.campaign_id)
        #app.logger.info("Camapaign Deleted Successfully")
    except Exception as e:
        app.logger.info(f"Error occured while deleting campaign cache")

    try:
        cache_all = cache.get_all()
        filtered_array = [str(element.decode()) if isinstance(element, bytes) else str(element) for element in cache_all if temp.campaign_id in str(element)]
        #app.logger.info("In line numb 97")
        for keys in filtered_array:
            cache.delete(keys)
        #app.logger.info("Indv keys deleted")
    except Exception as e:
        app.logger.info("Error - No campaign found for cleanup")

    return

def schedule_for_deletion(campaign_id, call_id, num, call_data):
    #app.logger.info(f"[{campaign_id}] Call Data {call_data}")
    #app.logger.info(f"[{campaign_id}] Scheduling for deletion of call_id: {call_id} of {num} with status {call_data['call_status']}")
    cache.delete(f"AUDIO_{campaign_id}_{num}")
    #app.logger.info(f"[{campaign_id}] Audio deleted for call_id: {call_id} of {num}")
    cache.delete(f'CALL_SESSION_{campaign_id}_{call_id}')
    #app.logger.info(f"[{campaign_id}] Call Session deleted for call_id: {call_id} of {num}")
    ongoing_document = ongoing_collection.find_one({"_id": call_id})
    #app.logger.info(f"[{campaign_id}] ongoing doc: {ongoing_document}")
    ongoing_document.pop("_id", None)
    payload_values = ongoing_document.get("payload", None)
    ongoing_document.pop("payload", None)
    if payload_values:
        ongoing_document.update(payload_values)
        ongoing_document["call_status"]= call_data["call_status"]
        ongoing_document["call_duration"]= call_data["call_duration"]
        ongoing_document["call_ended_time"]= call_data["call_ended_time"]

    #app.logger.info(f"[{campaign_id}] pop doc: {ongoing_document}")
    db_docs = new_completed_call.find_one({'_id': call_id})
    for key, value in ongoing_document.items():
        if key in db_docs:
            new_completed_call.update_one({"_id": call_id}, {'$set': {key: value}})
        else:
            new_completed_call.update_one({'_id': call_id}, {'$set': {key: value}})

    #app.logger.info(f"[{campaign_id}] data injected in mongodb")
    if call_data["call_status"] == 'unanswered' or call_data["call_status"] == 'failed' or call_data["call_status"] == 'drop':
      cache.delete_item(f'ONGOING_CALLS_{campaign_id}', call_id)
    #app.logger.info(f"[{campaign_id}] Ongoing call deleted for call_id: {call_id} of {num}")
    ongoing_collection.delete_one({"_id": call_id})
    check_campaign_completion = db.ongoing_collection.count_documents({})
    #app.logger.info(f"{check_campaign_completion} Document Count")

def make_call(campaign_id, number_name_id):
    response = callAPIRequest(campaignId=campaign_id, payload=number_name_id)
    if response:
        for call in number_name_id:
            call_id = call['clientid']
            phone_number = call['phoneno']
            current_node = "-1"
            call_status = "unanswered"
            call_initiated_time = (datetime.now() + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S")
            app.logger.info(
                f"[{campaign_id}] Call Initiated with call_id: {call_id}")
            cache.create_dict(f'ONGOING_CALLS_{campaign_id}', {call_id: phone_number})

            ongoing_collection.insert_one({"_id" : call_id},{"$set":{"number":phone_number}})#,"repeat_count":0}})

            #app.logger.info(f"[{campaign_id}] call_id: {call_id} of {phone_number} added to ongoing calls")

            cache.create_dict(f'CALL_SESSION_{campaign_id}_{call_id}', {'current_node': current_node,})

            new_completed_call.update_one({"_id": call_id}, {"$set": {"call_id": call_id, "campaign_id": campaign_id, "call_int_date":str((datetime.utcnow() + timedelta(hours=5, minutes=30)).date()), "call_int_time": call_initiated_time, "call_status": call_status, "current_node": current_node}})
        #app.logger.info(
        #    f"[{campaign_id}] [{call_id}] Call Session for {phone_number} Added")
    else:
        app.logger.error(f"[{campaign_id}] Call Initiation Failed")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Call Initiation Failed")

def initiate_calls(campaignid, queue, set_queue, number_of_call_to_be_made, voice_gender,language_id):
    number_name_id = []
    temp_phoneno = list(set_queue)[:number_of_call_to_be_made]
    #app.logger.info(f"[{campaignid}] calls to be made: {temp_phoneno}")
    for phone_number in temp_phoneno:
        call_id = uuid.uuid4().__str__()
        name = queue[phone_number]['CUSTOMER_NAME']
        queue[phone_number].pop("retry_count")
        result = None
        if result:###
            app.logger.info(f"[{campaignid}] User {phone_number} already exists")
        else:
            # queue[phone_number].update({"User_Profile_Date": str(datetime.now().date()), "User_Profile_Time": datetime.now().time().strftime("%H:%M:%S")})
            new_completed_call.insert_one({"_id": call_id, "phone_number": phone_number, "customer_name": name})
            app.logger.info(f"[{campaignid}] New user with {phone_number} created")
        app.logger.info(
                f"came till here")
        with open(f"Responses/responses_{voice_gender}_{language_id}.json") as f:
            json_data = json.load(f)
        with open(f"Encodings/encodings_{voice_gender}_{language_id}.pickle", 'rb') as f:
            prerecorded_encodings = pickle.load(f)
        audio_payload = get_prerecorded_encodings(queue[phone_number], json_data, prerecorded_encodings, voice_gender, language_id)
        cache.create_dict(f'AUDIO_{campaignid}_{phone_number}', audio_payload)
        app.logger.info(
            f"[{campaignid}] Audio Encoding for {phone_number} Added")
        number_name_id.append(
            {"phoneno": phone_number, "name": name, "clientid": call_id})
    app.logger.info(f"[{campaignid}] {number_name_id}")
    if number_name_id:
        make_call(campaign_id=campaignid, number_name_id=number_name_id)

# below function is used for creating connection with dialer api's
def callAPIRequest(campaignId, payload):
    url = "https://cubesoftservices.com/QuickCallRHICL/UploadLeadAiLifeBoT.php"
    data = "1;CLC@RHICL;"+json.dumps({
        "Priority": "2",
        "RemoveZero": "1",
        "RejectedLog": "1",
        "DuplicityCheck": "2",
        "EncryptedPhoneNo": "0",
        "AutoSaveExtraInfo": "1",
        "RemarksSuffix": "DDMMM",
        "FixedAgent": "",
        "CampaignId": campaignId,
        "FixedRemarks": "Default",
        "data": payload
    })
    app.logger.info(f"[{campaignId}] Calling API Request with payload: {data}")
    try:
        response = requests.request("POST", url, data=data)
        #app.logger.info(
        #    f"[{campaignId}] API Request response: {response.text}")
        if response.status_code == 200 and response.text != "":
            if str(response.json()["UploadLead"]) == "Success":
                res = response.json()['Response']
                app.logger.error(
                    f"[{campaignId}] Call Initiation successfull, Records:[{res['Records']}],Inserted:[{res['Inserted']}],Rejected:[{res['Rejected']}]")
                return True
            else:
                app.logger.error(
                    f"[{campaignId}] Call Initiation failed, recieved response [{response.json()['UploadLead']}]")
                return None
        else:
            app.logger.error(
                f"[{campaignId}] Call Initiation Failed via Dialer API")
            return None
    except:
        app.logger.error(
            f"[{campaignId}] Call Initiation Failed via Dialer API")
        return None


class CallStatus(BaseModel):
    call_id: str
    call_status: str
    call_duration: int
    campaign_id: str
    @validator('call_status')
    def check_status(cls, v):
        if v not in ["unanswered", "failed", "drop", "completed"]:
            raise HTTPException(status_code=400, detail="Invalid status")
        return v

# properties class is for schedule_call endpoints
class Properties(BaseModel):
    # voicebot_name: str
    # voicebot_id: str
    campaign_name: str
    campaign_id: str
    category: str
    language: str
    language_id: str
    retry_count: str
    note: str = None
    voice_gender: str
    time_range: str

class CallRecording(BaseModel):
	call_id: str
	campaign_id: str
	phone_number: str
	call_recording: HttpUrl

@app.get("/")
def root():
    return "Success!!"

@app.post("/schedule_calls")
def fetch_campaign(file: UploadFile = File(...), meta_data: Json = Form(Properties), api_key: APIKey = Depends(verify_dashboard_credentials)):
    temp = Properties(**meta_data)

    # Database deletion and cache cleanup
    delete_selected(detail_collection, queue_collection, ongoing_collection)
    clean_up(temp)
    app.logger.info("Clean Up Completed")

    if file.filename.endswith('.csv'):
        try:
            with BytesIO(file.file.read()) as xyz:
                df = pd.read_csv(xyz)
                app.logger.info(f"File read successfully, Data: {df}")
        except:
            app.logger.error(f"Error in parsing excel file")
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Error in parsing csv file")
        try:
            df["time_range"] = temp.time_range
            df["retry_count"] = temp.retry_count
            df.CUSTOMER_NAME = df.CUSTOMER_NAME.astype(str)
            df.PHONE_NUMBER = df.PHONE_NUMBER.astype(str)
        except:
            app.logger.error(f"Error in parsing excel file")
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Error in parsing data")
        num_cols = len(df.columns)
        phn_idx = df.columns.tolist().index("PHONE_NUMBER")
        payload = {i[phn_idx]:{df.columns[col]:i[col] for col in range(num_cols)} for i in df.to_dict(orient='split')['data']}
        # for pay_l in payload:
        #     payload[pay_l]['retry_count'] = 0
        payload_mongo = [{"number": row["PHONE_NUMBER"], "payload": {"retry_count": int(row["retry_count"]), "time_range": row["time_range"]}} for _, row in df.iterrows()]
        #allowed_campaigns = { f"{"}:"Retail"  } #database.get_campaigns()
        allowed_campaigns = { temp.campaign_id:temp.category}
        if allowed_campaigns:
            if temp.campaign_id not in allowed_campaigns.keys():
                app.logger.error(f"Campaign_id: {temp.campaign_id} not acceptable")
                raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Campaign_Id not acceptable...")
        else:
            app.logger.error(f"No campaigns found in allowed campaigns")
            raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="No campaigns found in allowed campaigns")
        campaign_details = {"Campaign_Details": {'language_id': temp.language_id,'retry_count': temp.retry_count, 'note': temp.note, 'voice_gender': temp.voice_gender, 'time_range': temp.time_range}}

        app.logger.info(f"Exported MongoDB collections and resetted the database")
        #cache.delete_all()
        #app.logger.info(f"Deleted all the keys from redis")
        try:
            try:
                campi_id = temp.campaign_id
                time_range_redi = temp.time_range
                # app.logger.info(f"time data for redis {temp.time_range}")
                # app.logger.info(f"CAMPAIGNS data for redis {campi_id}")
                cache.create_dict(f'DICT_{campi_id}', {campi_id:time_range_redi})
                campaigns = cache.get_dict(f'DICT_{campi_id}')
                #app.logger.info(f"CAMPAIGNS data sent into redis {campaigns}")
                campaign_details = {'_id':temp.campaign_id,
                                    "campingdetails":
                                        {'campaign_name':temp.campaign_name, 'category': temp.category, 'language':temp.language,'language_id': temp.language_id,'retry_count': temp.retry_count,'note': temp.note, 'voice_gender': temp.voice_gender, 'time_range': temp.time_range}}
                detail_collection.insert_one(campaign_details)
                #app.logger.info(f"[{temp.campaign_id}] Created Campaign Details!")
            except:
                app.logger.exception(f"Error in inserting campaign details")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Error in inserting campaign details")
            try:
                cache.set('QUEUE_'+temp.campaign_id, payload)
                queue_collection.insert_many(payload_mongo)
                app.logger.info(f"[{temp.campaign_id}] Created Queue!")
                return status.HTTP_200_OK
            except:
                app.logger.exception(f"Error in inserting queue")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Error in inserting queue")
        except:
            app.logger.exception(f"Error in creating campaign")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Error in creating campaign")
    else:
        app.logger.error("Invalid file type Recieved")
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Invalid file type Recieved")

@app.post("/status")
def call_status(meta_data: CallStatus, request: Request, api_key: APIKey = Depends(verify_dialer_credentials)):
    client_host = request.client
    call_id = meta_data.call_id
    call_status = meta_data.call_status
    duration = meta_data.call_duration
    campaign_id = meta_data.campaign_id
    #app.logger.info(f"[{campaign_id}] Recieved request from {client_host} for call id {call_id} | [{call_status}]")
    if cache.get_item(f"DICT_{campaign_id}", campaign_id):
        call_data = {}
        foo = cache.get_item("f'DICT_{campaign_id}'", campaign_id)
        app.logger.info(f"[{campaign_id}] Recieved cache {foo}")
        try:
            num = cache.get_dict(f'ONGOING_CALLS_{campaign_id}').get(call_id)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="inside voicebot - Cache data delete - Inserted new campaign")
        app.logger.info(f"[{campaign_id}] Recieved cache after searching against call_id {num}")
        if num:
            if call_status == "drop":
                call_status = "Attempted/Partially Completed"
            call_data["call_status"] = call_status
            call_data["call_duration"] = duration
            call_data["call_ended_time"] = (datetime.now() + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S")

            cache_queue = cache.get(f'QUEUE_{campaign_id}')
            if call_status == "failed" or call_status == "unanswered":
                num_queue = cache_queue.get(num)
                app.logger.info(
                     f"[{campaign_id}] Call failed for {num} | Queue Details: {num_queue}")
                retry_count = int(num_queue["retry_count"])
                doc = detail_collection.find_one({"_id": campaign_id})
                max_retry_count = int(doc["campingdetails"]["retry_count"])
                app.logger.info(f"[{campaign_id}] Call failed for {num} | retry_count: {retry_count} | Retry Count: {max_retry_count}")
                if retry_count == 0:
                    queue_collection.delete_one({'number': num})
                    cache_queue.pop(num)
                    app.logger.info(f"[{campaign_id}] Call failed for {num} | Removed from Queue | Queue Details: {cache_queue}")
                else:
                    queue_collection.update_one({"number":num},{"$set": {"payload.retry_count": retry_count - 1}})
                    cache_queue[num]["retry_count"] = retry_count - 1
                    app.logger.info(
                        f"[{campaign_id}] Call failed for {num} | Retry Count Updated")
            else:
                queue_collection.delete_one({'number': num})
                cache_queue.pop(num)
                app.logger.info(f"[{campaign_id}] Call completed for {num} | Removed from Queue")
            cache.set('QUEUE_'+campaign_id, cache_queue)
            schedule_for_deletion(campaign_id, call_id, num, call_data)
            return {"status": "success"}
        else:
            app.logger.error(f"Call_id: {call_id} not found in ongoing calls")
            raise HTTPException(status_code=404, detail="Call_Id not found...")
    else:
        app.logger.error(f"Campaign_id: {campaign_id} not found in campaigns")
        raise HTTPException(status_code=404, detail="Campaign_Id not found...")


@app.post("/recording")
def call_recording(meta_data: CallRecording, api_key: APIKey = Depends(verify_dialer_credentials)):
    call_id = meta_data.call_id
    campaign_id = meta_data.campaign_id
    call_recording = meta_data.call_recording
    phone_number = meta_data.phone_number
    #app.logger.info(f"[{campaign_id}] {call_id} recieved url: [{call_recording}]")
    if cache.get_item(f'DICT_{campaign_id}', campaign_id):
        result = new_completed_call.find_one({"_id": call_id})
        #print("call_recording",call_recording)
        call_recording = str(call_recording)
        if phone_number == result['phone_number']:
            try:
                app.logger.info(f"[{campaign_id}] {call_id} recieved url: [{call_recording}]")
                #call_recording = database.push_recording(campaign_id=campaign_id, call_id=call_id, recording_url=call_recording)
                # document = new_completed_call.find_one({"_id": call_id})
                # document[call_id]["call_recording"] = call_recording
                new_completed_call.update_one({"_id": call_id}, {"$set": {"call_recording": call_recording}})
                cache.delete_item(f'ONGOING_CALLS_{campaign_id}', call_id)
                app.logger.info(
                    f"[{campaign_id}] {call_id} recording updated in call session")
                return {"status": "success"}
            except Exception as e:
                app.logger.error(
                    f"[{campaign_id}] Error in pushing call recording: {e}")
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail="URL Provided is not a valid recording URL, Not Accessible or Invalid")
        else:
            app.logger.error(
                f"{phone_number} or {call_id} not found in campaign")
            raise HTTPException(
                status_code=404, detail="phone_number or call_id not found...")
    else:
        app.logger.error(f"Campaign_id: {campaign_id} not found in campaigns")
        raise HTTPException(status_code=404, detail="Campaign_Id not found...")


def process():
  while True:
    app.logger.info(f"First log True")
    campaigns = cache.get_dict(f'DICT_AiLife_CCOM04')
    app.logger.info(f"{campaigns} First campaign true")
    if campaigns:
      app.logger.info(f"{len(campaigns)} campaigns found")
      for campaignid, time_range in campaigns.items():
        date_, time_ = time_range.split("|")
        app.logger.info(f"[{campaignid}] {date_} {time_}")
        if check_date(date_):
          start, end = time_.split("-")
          app.logger.info(f"[{campaignid}] {start} - {end}")
          if isNowInTimeRange(start, end):
            queue = cache.get(f'QUEUE_{campaignid}')
            ongoing_calls = cache.get_dict(f'ONGOING_CALLS_{campaignid}')
            if ongoing_calls is None:
              ongoing_calls = dict()
            if queue is not None:
              if len(ongoing_calls) < PARALLEL_CALLS:
                ongoing_calls_number = {num for num in ongoing_calls.values()}

                app.logger.info(f"{ongoing_calls_number} for logger ongoing_call")
                set_queue = set(queue)
                app.logger.info(f"{set_queue} before")

                set_queue = set_queue - ongoing_calls_number
                app.logger.info(f"{set_queue} after")

                number_of_call_to_be_made = PARALLEL_CALLS - \
                  len(ongoing_calls_number)
                app.logger.info(f"{number_of_call_to_be_made} last")
                app.logger.info(f"[{campaignid}] {number_of_call_to_be_made} calls could be made...")
                app.logger.info(f"[queue is {queue}] set queue is{set_queue} calls could be made...")
                if detail_collection is not None:
                  app.logger.info(f"[{detail_collection.find()}] detail collection before initiate calls")
                  document = detail_collection.find_one({'_id': campaignid})
                  if document:
                      campingdetails = document.get('campingdetails', {})
                      voice_gender = campingdetails.get('voice_gender')
                      language_id = campingdetails.get('language_id')
                initiate_calls(campaignid, queue, set_queue, number_of_call_to_be_made,voice_gender,language_id)
            else:
              app.logger.info(f"[{campaignid}] No calls found in queue")
          else:
            app.logger.info(f"[{campaignid}] not in Time range [{start}-{end}]")
        else:
            app.logger.info(f"[{campaignid}] not in date range [{date_}]")
            continue
    else:
      app.logger.info("No campaigns found...")
    time.sleep(30)
thread = threading.Thread(target=process)
thread.start()
