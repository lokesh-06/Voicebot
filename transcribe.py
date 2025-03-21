import requests, os, time, logging, json, io, os, base64
from custom_logging import CustomizeLogger
from typing import Optional
from fastapi import Security, Depends, FastAPI, status, HTTPException, Request
from fastapi.security.api_key import APIKeyHeader, APIKey
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from Redis import Cache
from pymongo import MongoClient
from google.cloud import translate_v2 as translate
from utils import next_node
from pydub import AudioSegment
from googletrans import Translator
from google.cloud import speech_v1



translate_client = translate.Client()

with open("responses.json") as f:
    json_data = json.load(f)

client = MongoClient('mongodb://127.0.0.1:27017/?directConnection=true&serverSelectionTimeoutMS=2000&appName=mongosh+1.8.1')
db = client.DATABASE_AiLife_CCOM04
detail_collection = db.voicebot
ongoing_collection = db.ongoing
app = FastAPI(title='Transcribe API')
if not os.path.exists('logs'):
    os.makedirs('logs', exist_ok=True)

logger = logging.getLogger(__name__)
logger = CustomizeLogger.make_logger("logging_config.json")
app.logger = logger
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# app.logger.info("Models Initialization Successful...")
credential_path = "ailifebot-8fac6d214f8d.json"
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credential_path
translate_client = translate.Client()
cache = Cache()
# app.logger.info("Redis Cache Connection Successful...")
# app.logger.info("Database Connection Successful...")
api_key_header = APIKeyHeader(name="access_token", auto_error=False)
# app.logger.info("CallFlow Initialization Successful...")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path
class Audio(BaseModel):
    audio_data: Optional[str] = None
    call_id: str
    campaign_id: str

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],)

@app.get("/")
def root():
    return "Welcome to AI-LifeBot"


def translate_to_english(text,language_id):
    translator = Translator()
    translated_text = translator.translate(text, src=language_id, dest='en')
    
    return translated_text.text

def transcribe_base64_audio(audio_string, language_id):

    # Set up Google Cloud credentials
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path

    # Decode the base64-encoded audio string
    decoded_bytes = base64.b64decode(audio_string)

    # Convert the audio to mono and set the sample rate to 8000 Hz
    audio = AudioSegment.from_file(io.BytesIO(decoded_bytes))
    audio = audio.set_channels(1)
    audio = audio.set_frame_rate(8000)

    # Convert the audio to raw PCM data
    pcm_data = audio.raw_data
    sample_rate = 8000

    # Initialize the client
    client = speech_v1.SpeechClient()

    # Configure the audio settings
    audio_config = {
        "encoding": speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
        "sample_rate_hertz": sample_rate,
        "language_code": language_id,
    }
    config = speech_v1.RecognitionConfig(**audio_config)
    audio = {"content": pcm_data}

    # Perform the transcription
    response = client.recognize(config=config, audio=audio)

    if not response.results:
        return [""]

    # Process the transcription response
    transcripts = []
    for result in response.results:
        transcripts.append(result.alternatives[0].transcript)

    # Return the transcriptions
    return transcripts


@app.post("/transcribe", status_code=status.HTTP_200_OK)
def transcribe(audio: Audio, request: Request):
    request.app.logger.info(f"Start time - {time.perf_counter()}")
    client_host = request.client
    audio_string = audio.audio_data
    campaign_id = audio.campaign_id
    call_id = audio.call_id
    start_time = time.perf_counter()
    if audio_string == "":
        request.app.logger.error(
            f"[{campaign_id}] [{call_id}] Empty Audio String not allowed")
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Empty Audio String not allowed")
    if cache.get_item(f"DICT_{campaign_id}", campaign_id):
        request.app.logger.info(
            f"[{campaign_id}] Recieved request from {client_host} for call id {call_id}")
        language_id = detail_collection.find_one({"_id":campaign_id}, {"campingdetails.language_id": 1})["campingdetails"]["language_id"]
        start = time.perf_counter()
        try:
            num = cache.get_dict(f'ONGOING_CALLS_{campaign_id}').get(call_id)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="inside transcribe - Cache data delete - Inserted new campaign")
        if num:
            node_id = cache.get_item(
                f'CALL_SESSION_{campaign_id}_{call_id}', 'current_node')
            if not audio_string and node_id != "-1":
                request.app.logger.info(
                    f"[{campaign_id}] [{call_id}] Empty Audio String not allowed")
                raise HTTPException(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Empty Audio String not allowed")
            if audio_string:
                try:
                    # app.logger.info(f"{language_id}, Language id is here")
                    #app.logger.info(f"{audio_string}, audio_string is here")

                    transcription_time = time.perf_counter()

                    transcriptions = transcribe_base64_audio(audio_string, language_id)

                    transcribed_text = transcriptions[0]

                    #app.logger.info(f"{transcribed_text}, transcribed_text is here")

                    # url = "http://103.178.248.177:9005/speechtotext"
                    # payload = json.dumps({"language_id": language_id, "audio_data": audio_string})
                    # headers = {'Content-Type': 'application/json'}
                    # response = requests.request("POST", url, headers=headers, data=payload)

                    # if response.status_code == 200:
                    #     request.app.logger.info(
                    #     f"Transcription Request successfully executed...")
                    #     transcribed_text = response.json()['transcribed_text']
                    # else:
                    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transcription Failed...")

                    # transcribed_text = model.get_transcript(
                    #     audio_string, language_id)
                    request.app.logger.info(
                        f"[{campaign_id}] [{call_id}] Transcription Time: {time.perf_counter() - transcription_time}")
                except Exception as e:
                    # raise e
                    request.app.logger.error(
                        f"[{call_id}] Error in transcribe")
                    # return
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail="Transcription Failed...")
                request.app.logger.info(
                    f"[{campaign_id}] [{call_id}] Transcription: {transcribed_text}")
                if language_id:# == "en" or language_id == "hi":
                    converted_text = transcribed_text
                    app.logger.info(f"{converted_text} Converted text after language_id check")
                else:
                    try:
                        conversion_time = time.perf_counter()
                        trans_data = {"q": transcribed_text, "source": 'en', "target": language_id}
                        result = translate_client.translate(trans_data['q'], source_language=trans_data['target'], target_language=trans_data['source'])
                        converted_text = result['translatedText']
                        # request.app.logger.info(
                        #     f"[{campaign_id}] [{call_id}] Conversion Time: {time.perf_counter() - conversion_time}")
                    except:
                        request.app.logger.error(
                            f"[{call_id}] Error in convert")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, detail="Conversion Failed...")
                    request.app.logger.info(
                        f"[{campaign_id}] [{call_id}] In English: {converted_text}, {type(converted_text)} ")
                # request.app.logger.info(
                #     f"[{campaign_id}] [{call_id}] Intent Check: {json_data['nodes'][node_id]['intent_check_list']}")
                if language_id =="hi":
                    try:
                        #converted_text = translate_to_english(converted_text,language_id) #english translate
                        converted_text = translate_client.translate(converted_text, source_language=language_id, target_language="en")
                        converted_text = converted_text['translatedText']
                    except:
                        converted_text=""
                else:
                    converted_text = converted_text
                if json_data['nodes'][node_id]['intent_check_list'] != "False":
                    app.logger.info(f"{converted_text} Converted text before try block and {type(converted_text)}")

                    try:
                        intent_time = time.perf_counter()
                        #if converted_text == "":
                        #  intent = ""
                        #else:
                        #if language_id:
                        #  try:
                        #    converted_text = translate_to_english(converted_text,language_id) #english translate
                        #  except:
                        #    converted_text=""
                        intent_data = {"text": converted_text, "intent_list": json_data['nodes'][node_id]['intent_check_list']}
                        request.app.logger.info(f"[{campaign_id}] intent_data: {intent_data}")
                        intent_url = "http://127.0.0.1:9099/get_intent"
                        request.app.logger.info(f"[{campaign_id}] intent_url: {intent_url}")
                        headers = {'Content-Type': 'application/json'}
                        request.app.logger.info(f"[{campaign_id}] headers: {headers}")
                        intent_payload = json.dumps(intent_data)
                        request.app.logger.info(f"[{campaign_id}] intent_payload: {intent_payload}")
                        response = requests.request("POST", intent_url, headers= headers, data= intent_payload)
                        request.app.logger.info(f"[{campaign_id}] Response status code: {response.status_code}")
                        request.app.logger.info(f"[{campaign_id}] Response content: {response.content}")
                        if response.status_code == 200:
                            intent = response.json()['intent']
                        else:
                            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                                detail="Intent classification Failed...")
                        # request.app.logger.info(
                        #     f"[{campaign_id}] [{call_id}] Intent: {intent}")
                        # request.app.logger.info(
                        #     f"[{campaign_id}] [{call_id}] intent Time: {time.perf_counter() - intent_time}")
                    except:
                        request.app.logger.error(f"[{call_id}] Error in intent")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, detail="intent Failed...")
                    # request.app.logger.info(
                    #     f"[{campaign_id}] [{call_id}] Intent: {intent}")
                    # request.app.logger.info(
                    #     f"[{campaign_id}] Transcription, Conversion and intent in: {time.perf_counter() - start}")
                else:
                    intent = None

            ##
            try:
              if intent =="Repeat":# or (language_id=='hi' and intent==""):
                on_call = ongoing_collection.find_one({"_id": call_id})
                nodeid = int(node_id)
                if "repeat_count" in on_call.keys():
                  repeat_node = int(on_call["repeat_node"])
                  if repeat_node == nodeid:
                    new_repeat_count = int(on_call["repeat_count"]) + 1
                    ongoing_collection.update_one({"_id" : call_id},{"$set": {"repeat_count": new_repeat_count}})
                    ongoing_collection.update_one({"_id" : call_id},{"$set": {"repeat_node": int(nodeid)}})
                  else:
                    ongoing_collection.update_one({"_id" : call_id},{"$set": {"repeat_count": 0}})
                    ongoing_collection.update_one({"_id" : call_id},{"$set": {"repeat_node": int(nodeid)}})
                else:
                  ongoing_collection.update_one({"_id" : call_id},{"$set": {"repeat_count": 0}})
                  ongoing_collection.update_one({"_id" : call_id},{"$set": {"repeat_node": int(nodeid)}})
            except:
              pass

            check_repeats = ongoing_collection.find_one({"_id": call_id})
            try:
              repeat_num = check_repeats["repeat_count"]
            except:
              repeat_num = 0


            if repeat_num == 2:
              end_call = True

              audio_response = cache.get_item(f'AUDIO_{campaign_id}_{num}', "12")
              content = {"end_call": end_call, "response": audio_response, "pause":{'waittime': '', 'silencetime': ''}}
              #content = {"end_call": end_call, "response": audio_response}
              headers = {"content-type": "application/json; charset=UTF-8"}
            ##
            else:

              start = time.perf_counter()
              end_call = False
              if node_id == "-1":
                  node = json_data['nodes']["0"]
                  #pause = json_data['nodes']["0"]["pause"]
                  pause = {'waittime': '2', 'silencetime': '1'}
                  request.app.logger.info(
                      f"[{pause}] pause times if condition node -1")
                  context = None
                  audio_response = cache.get_item(
                      f'AUDIO_{campaign_id}_{num}', node['node_id'])
                  # request.app.logger.info(
                  #     f"[{campaign_id}] Get Audio Encoding in: {time.perf_counter() - start}")
                  start = time.perf_counter()
                  try:
                      cache.set_item(
                          f'CALL_SESSION_{campaign_id}_{call_id}', 'current_node', '0')
                      # request.app.logger.info(
                      #     f"[{campaign_id}] Set Current Node in: {time.perf_counter() - start}")
                  except Exception as e:
                      request.app.logger.error(f"[{campaign_id}] Error making request to cache: {e}")
                  start = time.perf_counter()
                  ongoing_collection.update_one({"_id" : call_id},{"$set":{"payload":{"call_status": "inprogress", "current_node": "0"}, "number": num}})
                  # request.app.logger.info(
                  #     f"[{campaign_id}] Update Call in: {time.perf_counter() - start}")

              else:
                  node = json_data['nodes'][node_id]
                  request.app.logger.info(
                      f"[{node}] node variable in else block")
                  pause = json_data['nodes'][node_id]["pause"]
                  request.app.logger.info(
                      f"[{pause}] pause times else condition nodeid dynamic")
                  context = None
                  if node['conv_step_name']:
                      context_set_time = time.perf_counter()
                      context = {node['conv_step_name']: {"text": transcribed_text,
                                                "english": converted_text, "intent": intent}}
                      cache.set_item(
                          f'CALL_SESSION_{campaign_id}_{call_id}', 'context', str(context))
                      # request.app.logger.info(
                      #     f"[{campaign_id}] Context Set Time: {time.perf_counter() - context_set_time}")
                      database_update_time = time.perf_counter()
                      ongoing_collection.update_one({"_id" : call_id},{"$push":{"context":context}})
                  #     request.app.logger.info(
                  #         f"[{campaign_id}] Database Update Time: {time.perf_counter() - database_update_time}")
                  # request.app.logger.info(
                  #     f"[{campaign_id}] Get Current Node and Context in: {time.perf_counter() - start}")
                  try:
                      next_node_set_time = time.perf_counter()
                      node = next_node(node, intent,json_data)
                      cache.set_item(
                          f'CALL_SESSION_{campaign_id}_{call_id}', 'current_node', node['node_id'])
                      # request.app.logger.info(
                      #     f"[{campaign_id}] Next Node Set Time: {time.perf_counter() - next_node_set_time}")
                      database_update_call_time = time.perf_counter()
                      ongoing_collection.update_one({"_id": call_id}, {"$set": {"payload.current_node": node['node_id'], "number": num}})
                      # request.app.logger.info(
                      #     f"[{campaign_id}] Database Update Call Time: {time.perf_counter() - database_update_call_time}")
                      # request.app.logger.info(
                      #     f"[{campaign_id}] Get Next Node in: {time.perf_counter() - start}")
                      audio_response = cache.get_item(
                          f'AUDIO_{campaign_id}_{num}', node['node_id'])
                      # request.app.logger.info(
                      #     f"[{campaign_id}] Get Audio Encoding in: {time.perf_counter() - start}")
                  except:
                      request.app.logger.error(
                          f"[{campaign_id}] [{call_id}] Call Flow Ended")
                      raise HTTPException(
                          status_code=status.HTTP_400_BAD_REQUEST, detail="Next Node Failed...")
                  if "user_reply" not in node:
                      end_call = True
              content = {"end_call": end_call, "response": audio_response, "pause": pause}
              headers = {"content-type": "application/json; charset=UTF-8"}
              request.app.logger.info(f"End time - {time.perf_counter()}")
              # request.app.logger.info(
              #     f"[{campaign_id}] [{call_id}] API Total Response Time: {time.perf_counter() - start_time}")
              request.app.logger.info(
                      f"[{content['pause']}] last content pausecheck")
            return JSONResponse(content=content, headers=headers)
        else:
            # request.app.logger.error(
            #     f"[{campaign_id}] [{call_id}] No Ongoing Calls, Call Id not found...")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Call Id not found")
    else:
        # request.app.logger.error(
        #     f"[{campaign_id}] [{call_id}] Campaign Id not found...")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Campaign Id not found")
            
            
@app.get("/check")
def check():
  return "Transcribe check"
