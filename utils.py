import os
import base64
import uuid
import pydub
from pydub import AudioSegment
from io import BytesIO
import google.cloud.texttospeech as tts
import logging
from custom_logging import CustomizeLogger
from googletrans import Translator

#voice = "en-IN-Wavenet-D"#"hi-IN-Neural2-C"# "en-IN-Wavenet-B"


voice_mapping = {
    ("male", "en"): "en-IN-Wavenet-B",
    ("female", "en"): "en-IN-Wavenet-D",
    ("male", "hi"): "hi-IN-Neural2-C",
    ("female", "hi"): "hi-IN-Standard-D",
}


def get_voice(voice_gender, language):
    return voice_mapping.get((voice_gender, language))


logger = logging.getLogger(__name__)
logger = CustomizeLogger.make_logger("logging_config.json")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "ailifebot-8fac6d214f8d.json"

def translate_to_hindi(text,language_id):
    translator = Translator()
    translated_text = translator.translate(text, src='en', dest=language_id)
    return translated_text.text

def key_updating_audio(dict1, json_data, y_prerecorded_encodings=None):
  for ele in dict1:
    if ele in json_data['var']:
      nodes_to_update = json_data['var'][ele]
      for nod_id in nodes_to_update:
        if isinstance(y_prerecorded_encodings[nod_id], str):
            y_prerecorded_encodings[nod_id] = y_prerecorded_encodings[nod_id].replace(f"var({ele})", dict1[ele])
        else:
            print(f"Unexpected data type: {type(y_prerecorded_encodings[nod_id])}")
            #y_prerecorded_encodings[nod_id] = y_prerecorded_encodings[nod_id].replace(f"var({ele})", dict1[ele])
  return y_prerecorded_encodings

## Audio Fetching Logic
def base_64_converter(sound):
  # sound = new_prerecorded_encodings[prev_key]
  file_name = "tmp/"+str(uuid.uuid4())+".wav"
  sound = sound.set_frame_rate(8000)
  sound.export(file_name, format="wav")
  sound = base64.b64encode(open(file_name, "rb").read())
  os.remove(file_name)
  # new_prerecorded_encodings[prev_key] = sound
  return sound

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
"""
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
    sound.export(file_name, format="wav",bitrate="128k")
    sound = base64.b64encode(open(file_name, "rb").read())
    os.remove(file_name)
    return sound
"""
similar_groups = {}
converted_groups = {}

def similar_group(enco, voice,language_id):
  for key in enco:
      prefix = key.split('-')[0]  # Extract the prefix before the hyphen
      if prefix not in similar_groups:
          similar_groups[prefix] = {}
      similar_groups[prefix][key] = enco[key]

  start_key = 0
  for group in similar_groups.values():
    for key, value in group.items():
        if isinstance(value, str):
            #if voice.split("-")[0]== language_id:
            #  value = translate_to_hindi(value,language_id)     #audio translated to hindi
            value = text_to_wav(voice, value)
            value = AudioSegment.from_wav(BytesIO(value))
            group[key] = value
        elif not isinstance(value, bytes):
            value = base_64_converter(value)
        converted_groups[str(start_key)] = value
        start_key += 1
  return similar_groups

def final_encoding(similar_groups):
    new_dict = {}
    index = 0
    for group, sub_dict in similar_groups.items():
        merged_audio = None
        for key, value in sub_dict.items():
            if isinstance(value, AudioSegment):
                if merged_audio is None:
                    merged_audio = value
                else:
                    merged_audio += value
            else:
                new_dict[index] = value

        if merged_audio is not None:
            merged_audio = base_64_converter(merged_audio)
            new_dict[index] = merged_audio
        index += 1
    return new_dict

def get_prerecorded_encodings(dict1, json_data, prerecorded_encodings, voice_gender, language_id):

  logger.info(f"Json data var is {json_data['var']} ")
  logger.info(f"input for  get_prerecorded_encodings is {dict1} ")
  dict1 = {ele:dict1[ele] for ele in dict1 if ele in json_data['var']}
  logger.info(f"sampled input is {dict1} ")
  x_prerecorded_encodings = key_updating_audio(dict1, json_data, prerecorded_encodings)
  #logger.info(f"After Key updates in audio file is {prerecorded_encodings} ")
  # new_prerecorded_encodings = audio_fetch_logic(json_data, prerecorded_encodings)
  #logger.info(f"new_prerecorded_encodings is {new_prerecorded_encodings} ")
  # return new_prerecorded_encodings
  
  voice = get_voice(voice_gender, language_id)
  converted_encodings = similar_group(x_prerecorded_encodings, voice,language_id)
  new_prerecorded_encodings = final_encoding(converted_encodings)
  return new_prerecorded_encodings

def next_node(node, intent,json_data):
  if node['intent_check_list'] and node['intent_check_list'] != "False":
    for intent_ele in node['user_reply']['element']:
        if intent.lower() == intent_ele['intent'].lower():
            node_id = str(intent_ele['next_node_id'])
            return json_data['nodes'][node_id]

    return node
  else:
     node_id = str(node['user_reply']['element'][0]['next_node_id'])
     return json_data['nodes'][node_id]
