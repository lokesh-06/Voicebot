import json
from tqdm import tqdm
import pickle
import uuid
from pydub import AudioSegment
from io import BytesIO
import google.cloud.texttospeech as tts
import os
import base64
from googletrans import Translator
from google.cloud import translate_v2 as translate
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "ailifebot-8fac6d214f8d.json"
translate_client = translate.Client()


gender = 'male'
language_id = 'en'

with open(f"Responses/responses_{gender}_{language_id}.json") as f:
  json_data = json.load(f)

dynamic_list = []
for d_key in json_data['var']:
  for ele in json_data['var'][d_key]:
    dynamic_list.append(ele.split("-")[0])

prerecorded_encodings = {}
#voice = "en-IN-Wavenet-C"

voice_mapping = {
    ("male", "en"): "en-IN-Wavenet-B",
    ("female", "en"): "en-IN-Wavenet-D",
    ("male", "hi"): "hi-IN-Neural2-C",
    ("female", "hi"): "hi-IN-Standard-D",
}

def get_voice(voice_gender, language):
    return voice_mapping.get((voice_gender, language))
    
def translate_to_hindi(text):
    translator = Translator()
    translated_text = translator.translate(text, src='en', dest='en')
    return translated_text.text

voice= get_voice(gender,language_id)

#os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "ailifebot-8fac6d214f8d.json"
def text_to_wav(voice_name: str, text: str):
    language_code = "-".join(voice_name.split("-")[:2])
    text_input = tts.SynthesisInput(text=text)
    voice_params = tts.VoiceSelectionParams(
        language_code=language_code, name=voice_name,

    )
    audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16, speaking_rate=0.93)

    client = tts.TextToSpeechClient()
    response = client.synthesize_speech(
        input=text_input, voice=voice_params, audio_config=audio_config
    )
    return response.audio_content

def get_name_enc(name, voice):
    name_audio = text_to_wav(voice, name)
    name_audio = AudioSegment.from_wav(BytesIO(name_audio))
    name_audio = name_audio.set_channels(1)
    name_audio = name_audio.set_frame_rate(8000)
    return name_audio

def get_encoding(chunk_list, name_enc=None, prerecorded_outputs=None, voice=None):
    sound = None
    if not os.path.exists("tmp"):
        os.makedirs("tmp")
    for chunk in chunk_list:
        if chunk == "name":
            x = name_enc
        else:
            if chunk in prerecorded_outputs.keys():
                x = prerecorded_outputs[chunk]
            else:
                tmp = text_to_wav(voice, chunk)
                x = AudioSegment.from_wav(BytesIO(tmp))
                x = x.set_channels(1)
                x = x.set_frame_rate(8000)
        if sound:
            sound = sound + x
        else:
            sound = x
    sound = sound.set_frame_rate(8000)
    file_name = "tmp/"+str(uuid.uuid4())+".wav"
    sound.export(file_name, format="wav")
    sound = base64.b64encode(open(file_name, "rb").read())
    os.remove(file_name)
    return sound

os.makedirs("tmp",exist_ok=True)
for nod_id in json_data["nodes"]:
    for ele in json_data["nodes"][nod_id]['bot_reply']['element']:
        if ele['encoding_key']:
            key = ele['encoding_key']
        else:
            key = nod_id
        
        sample = ele['string']
        if language_id=='en': 
          sample_translate = translate_client.translate(sample, source_language="en", target_language="hi")
          sample = sample_translate['translatedText']
        if eval(ele['encoding']):
          sample = ele['string']
          print(sample)
          audio = text_to_wav(voice, sample)
          audio = AudioSegment.from_wav(BytesIO(audio))
          if key in prerecorded_encodings:
              print(True)
              #audio_1 = prerecorded_encodings[key]
              #audio_2 = audio
              #audio_2 = AudioSegment.from_wav(BytesIO(audio_2))
              #audio = audio_1 + AudioSegment.silent(duration=1500) + audio_2
              #sample = sample[0] + " " + sample[1]

          audio = audio.set_channels(1)
          audio = audio.set_frame_rate(8000)
          if nod_id not in dynamic_list:
            file_name = "tmp/"+str(uuid.uuid4())+".wav"
            audio.export(file_name, format="wav",bitrate="128k")
            audio = base64.b64encode(open(file_name, "rb").read())
          prerecorded_encodings[key] = audio
        else:
          #if language_id=='hi': 
          #  ele['string'] = translated_text
          prerecorded_encodings[key] = ele['string']
#print(prerecorded_encodings)
os.makedirs("Encodings",exist_ok=True)
with open(f"Encodings/encodings_{gender}_{language_id}.pickle", "wb") as f:
    pickle.dump(prerecorded_encodings, f)
