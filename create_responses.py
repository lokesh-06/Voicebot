import json
import os
import pickle
import re
from googletrans import Translator
from google.cloud import translate_v2 as translate


gender = 'male'  #to be converted
language_id = 'en'  #to be converted (hindi)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "ailifebot-8fac6d214f8d.json"
translate_client = translate.Client()

#with open("responses.json") as f:
#  json_data = json.load(f)
encodings_to_try = ['ISO-8859-1']
# Function to attempt loading JSON with different encodings
def load_json_with_encoding(file_path):
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                return json.load(file)
        except UnicodeDecodeError:
            print(f"Failed to decode JSON with {encoding} encoding. Trying the next one...")
            continue
    print("Error: Unable to decode the JSON file with any of the specified encodings.")
    return None
    
# File path to your JSON file
file_path = "responses.json"

# Attempt to load JSON with different encodings
json_data = load_json_with_encoding(file_path)
json_data
def translate_to_hindi(text):
    translator = Translator()
    translated_text = translator.translate(text, src='en', dest='hi')
    return translated_text.text

for nod_id in json_data["nodes"]:
  if language_id == 'hi': 
    json_data['nodes'][nod_id]['languageID'] = 'en'
  for ele in json_data["nodes"][nod_id]['bot_reply']['element']:
    if gender=='female' and 'Manoj' in ele['string']:
      ele['string'] = ele['string'].replace('Victor', 'Pujaa')
    if re.search(r'var \(customer_name\)', ele['string']):
      ele['string'] = ele['string'].replace('var (customer_name)', 'var(CUSTOMER_NAME)')
    if language_id == 'hi':
      ele['string'] = translate_client.translate(ele['string'], source_language="en", target_language="hi")['translatedText']#translate_to_hindi(ele['string'])
    if re.search(r'var \(customer_name\)', ele['string']):
      ele['string'] = ele['string'].replace('var (customer_name)', 'var(CUSTOMER_NAME)')
      
os.makedirs("Responses",exist_ok=True)
with open(f"Responses/responses_{gender}_{language_id}.json", "w") as json_file:
     json.dump(json_data, json_file,indent=2, ensure_ascii=False)
  

