# -*- coding: utf-8 -*-

#
# Author: Roland Pihlakas, 2023 - 2023
#
# roland@simplify.ee
#


if __name__ == '__main__':
  print("Starting...")


import os
import sys
import traceback
import httpcore
import httpx

from configparser import ConfigParser

# import spacy
# from spacy import displacy    # load it only when rendering is requested, since this package loads slowly

import re
from collections import defaultdict, Counter, OrderedDict
import hashlib
import string
import base64

import rapidfuzz.process
import rapidfuzz.fuzz
from fuzzysearch import find_near_matches

import json_tricks

# import openai
import tenacity   # for exponential backoff
import openai_async
import tiktoken

##For looping with 6 ms delay to maintain OpenAI API limit
#import asyncio
#from tenacity import retry, stop_after_delay, wait_fixed


# organization = os.getenv("OPENAI_API_ORG")
api_key = os.getenv("OPENAI_API_KEY")

# openai.organization = organization
# openai.api_key = api_key


from Utilities import init_logging, safeprint, print_exception, loop, debugging, is_dev_machine, data_dir, Timer, read_file, save_file, read_raw, save_raw, read_txt, save_txt, strtobool, async_cached, async_cached_encrypted
from TimeLimit import time_limit


# if __name__ == "__main__":
#   init_logging(os.path.basename(__file__), __name__, max_old_log_rename_tries = 1)


if __name__ == "__main__":
  os.chdir(os.path.dirname(os.path.realpath(__file__)))

if is_dev_machine:
  from pympler import asizeof




def remove_quotes(text):
  return text.replace("'", "").replace('"', '')


def rotate_list(list, n):
  return list[n:] + list[:n]


def get_config():

  config = ConfigParser(inline_comment_prefixes=("#", ";"))  # by default, inline comments were not allowed
  config.read('MER.ini')

  
  gpt_model = remove_quotes(config.get("MER", "GPTModel", fallback="gpt-3.5-turbo-16k")).strip()
  gpt_timeout = int(remove_quotes(config.get("MER", "GPTTimeoutInSeconds", fallback="60")).strip())
  extract_message_indexes = strtobool(remove_quotes(config.get("MER", "ExtractMessageIndexes", fallback="false")))
  do_open_ended_analysis = strtobool(remove_quotes(config.get("MER", "DoOpenEndedAnalysis", fallback="true")))
  do_closed_ended_analysis = strtobool(remove_quotes(config.get("MER", "DoClosedEndedAnalysis", fallback="true")))
  keep_unexpected_labels = strtobool(remove_quotes(config.get("MER", "KeepUnexpectedLabels", fallback="true")))
  chart_type = remove_quotes(config.get("MER", "ChartType", fallback="radar")).strip()
  render_output = strtobool(remove_quotes(config.get("MER", "RenderOutput", fallback="false")))
  create_pdf = strtobool(remove_quotes(config.get("MER", "CreatePdf", fallback="true")))
  treat_entire_text_as_one_person = strtobool(remove_quotes(config.get("MER", "TreatEntireTextAsOnePerson", fallback="false")))  # TODO
  anonymise_names = strtobool(remove_quotes(config.get("MER", "AnonymiseNames", fallback="false")))
  anonymise_numbers = strtobool(remove_quotes(config.get("MER", "AnonymiseNumbers", fallback="false")))
  named_entity_recognition_model = remove_quotes(config.get("MER", "NamedEntityRecognitionModel", fallback="en_core_web_sm")).strip()
  encrypt_cache_data = strtobool(remove_quotes(config.get("MER", "EncryptCacheData", fallback="false")))
  split_messages_by = remove_quotes(config.get("MER", "SplitMessagesBy", fallback="")) # .strip()
  ignore_incorrectly_assigned_citations = strtobool(remove_quotes(config.get("MER", "IgnoreIncorrectlyAssignedCitations", fallback="false")))
  allow_multiple_citations_per_message = strtobool(remove_quotes(config.get("MER", "AllowMultipleCitationsPerMessage", fallback="true")))
  citation_lookup_time_limit = float(remove_quotes(config.get("MER", "CitationLookupTimeLimit", fallback="0.1")))


  result = { 
    "gpt_model": gpt_model,
    "gpt_timeout": gpt_timeout,
    "extract_message_indexes": extract_message_indexes,
    "do_open_ended_analysis": do_open_ended_analysis,
    "do_closed_ended_analysis": do_closed_ended_analysis,
    "keep_unexpected_labels": keep_unexpected_labels,
    "chart_type": chart_type,
    "render_output": render_output,
    "create_pdf": create_pdf,
    "treat_entire_text_as_one_person": treat_entire_text_as_one_person,
    "anonymise_names": anonymise_names,
    "anonymise_numbers": anonymise_numbers,
    "named_entity_recognition_model": named_entity_recognition_model,
    "encrypt_cache_data": encrypt_cache_data,
    "split_messages_by": split_messages_by,
    "ignore_incorrectly_assigned_citations": ignore_incorrectly_assigned_citations,
    "allow_multiple_citations_per_message": allow_multiple_citations_per_message,
    "citation_lookup_time_limit": citation_lookup_time_limit,
  }

  return result

#/ get_config()


## https://platform.openai.com/docs/guides/rate-limits/error-mitigation
@tenacity.retry(wait=tenacity.wait_random_exponential(min=1, max=60), stop=tenacity.stop_after_attempt(6))   # TODO: config parameters
async def completion_with_backoff(gpt_timeout, **kwargs):  # TODO: ensure that only HTTP 429 is handled here

  # return openai.ChatCompletion.create(**kwargs) 

  qqq = True  # for debugging

  attempt_number = completion_with_backoff.retry.statistics["attempt_number"]
  timeout_multiplier = 2 ** (attempt_number-1) # increase timeout exponentially

  try:

    timeout = gpt_timeout * timeout_multiplier

    safeprint(f"Sending OpenAI API request... Using timeout: {timeout} seconds")

    openai_response = await openai_async.chat_complete(
      api_key,
      timeout = timeout, 
      payload = kwargs
    )

    safeprint("Done OpenAI API request.")


    openai_response = json_tricks.loads(openai_response.text)

    if openai_response.get("error"):
      raise Exception(openai_response["error"]["message"]) # TODO: use a more specific exception type

    # NB! this line may also throw an exception if the OpenAI announces that it is overloaded # TODO: do not retry for all error messages
    response_content = openai_response["choices"][0]["message"]["content"]
    finish_reason = openai_response["choices"][0]["finish_reason"]

    return (response_content, finish_reason)

  except Exception as ex:   # httpcore.ReadTimeout

    if type(ex) is httpcore.ReadTimeout or type(ex) is httpx.ReadTimeout:	# both exception types have occurred
      if attempt_number < 6:    # TODO: config parameter
        safeprint("Read timeout, retrying...")
      else:
        safeprint("Read timeout, giving up")
    else:
      msg = str(ex) + "\n" + traceback.format_exc()
      print_exception(msg)

    raise

#/ async def completion_with_backoff(gpt_timeout, **kwargs):


# https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def num_tokens_from_messages(messages, model):
  """Return the number of tokens used by a list of messages."""

  try:
    encoding = tiktoken.encoding_for_model(model)
  except KeyError:
    safeprint("Warning: model not found. Using cl100k_base encoding.")
    encoding = tiktoken.get_encoding("cl100k_base")

  if model in {
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-16k-0613",
    "gpt-4-0314",
    "gpt-4-32k-0314",
    "gpt-4-0613",
    "gpt-4-32k-0613",
  }:
    tokens_per_message = 3
    tokens_per_name = 1

  elif model == "gpt-3.5-turbo-0301":
    tokens_per_message = 4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
    tokens_per_name = -1  # if there's a name, the role is omitted

  elif "gpt-3.5-turbo" in model:
    # safeprint("Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0613.")
    return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0613")

  elif "gpt-3.5-turbo-16k" in model: # roland
    # safeprint("Warning: gpt-3.5-turbo-16k may update over time. Returning num tokens assuming gpt-3.5-turbo-16k-0613.")
    return num_tokens_from_messages(messages, model="gpt-3.5-turbo-16k-0613")

  elif "gpt-4" in model:
    # safeprint("Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613.")
    return num_tokens_from_messages(messages, model="gpt-4-0613")

  else:
    #raise NotImplementedError(
    #  f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens."""
    #)
    safeprint(f"num_tokens_from_messages() is not implemented for model {model}")
    # just take some conservative assumptions here
    tokens_per_message = 4
    tokens_per_name = 1


  num_tokens = 0
  for message in messages:

    num_tokens += tokens_per_message

    for key, value in message.items():

      num_tokens += len(encoding.encode(value))
      if key == "name":
        num_tokens += tokens_per_name

    #/ for key, value in message.items():

  #/ for message in messages:

  num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>


  return num_tokens

#/ def num_tokens_from_messages(messages, model):


async def run_llm_analysis_uncached(model_name, gpt_timeout, messages, continuation_request):

  responses = []


  # TODO: config  
  if model_name == "gpt-3.5-turbo-16k": # https://platform.openai.com/docs/models/gpt-3-5
    max_tokens = 16384
  elif model_name == "gpt-4": # https://platform.openai.com/docs/models/gpt-4
    max_tokens = 8192
  elif model_name == "gpt-3.5-turbo": # https://platform.openai.com/docs/models/gpt-3-5
    max_tokens = 4096
  else:
    max_tokens = 4096


  continue_analysis = True
  while continue_analysis:

    num_input_tokens = num_tokens_from_messages(messages, model_name)
    safeprint(f"num_input_tokens: {num_input_tokens} max_tokens: {max_tokens}")

    #if num_tokens <= 0:
    #  break


    buffer_tokens = 100 # just in case to not trigger OpenAI API errors # TODO: config

    (response_content, finish_reason) = await completion_with_backoff(

      gpt_timeout,

      model = model_name,
      messages = messages,
          
      # functions = [],   # if no functions are in array then the array should be omitted, else error occurs
      # function_call = "none",   # 'function_call' is only allowed when 'functions' are specified
      n = 1,
      stream = False,   # TODO
      # user = "",    # TODO

      temperature = 0, # 1,   0 means deterministic output
      top_p = 1,
      max_tokens = max_tokens - num_input_tokens - 1 - buffer_tokens,  # need to subtract number of input tokens, else we get an error from OpenAI # NB! need to substract an additional 1 token else OpenAI is still not happy: "This model's maximum context length is 8192 tokens. However, you requested 8192 tokens (916 in the messages, 7276 in the completion). Please reduce the length of the messages or completion."
      presence_penalty = 0,
      frequency_penalty = 0,
      # logit_bias = None,
    )

    responses.append(response_content)
    too_long = (finish_reason == "length")

    if too_long:
      messages.append({"role": "assistant", "content": response_content})
      messages.append({"role": "assistant", "content": continuation_request})   # TODO: test this functionality
    else:
      continue_analysis = False

  #/ while continue_analysis:

  response = "\n".join(responses)
  return response

#/ async def run_llm_analysis_uncached():


async def run_llm_analysis(config, model_name, gpt_timeout, messages, continuation_request, enable_cache = True):

  encrypt_cache_data = config["encrypt_cache_data"]

  if encrypt_cache_data:
    result = await async_cached_encrypted(1 if enable_cache else None, run_llm_analysis_uncached, model_name, gpt_timeout, messages, continuation_request)
  else:
    result = await async_cached(1 if enable_cache else None, run_llm_analysis_uncached, model_name, gpt_timeout, messages, continuation_request)

  return result

#/ async def run_llm_analysis():


def remove_comments(text):
  # re.sub does global search and replace, replacing all matching instances
  text = re.sub(r"(^|[\r\n]+)\s*#[^\r\n]*", "", text)
  return text
#/ def remove_comments(text):


def sanitise_input(text):
  # re.sub does global search and replace, replacing all matching instances
  text = re.sub(r"[{\[]", "(", text)
  text = re.sub(r"[}\]]", ")", text)
  text = re.sub(r"-{3,}", "--", text)   # TODO: use some other separator between system instruction and user input
  return text
#/ def sanitise_input(text):


def anonymise_uncached(user_input, anonymise_names, anonymise_numbers, ner_model):

  safeprint("Loading Spacy...")
  import spacy    # load it only when anonymisation is requested, since this package loads slowly

  safeprint("Loading Named Entity Recognition model...")
  NER = spacy.load(ner_model)   # TODO: config setting


  entities = NER(user_input)
  letters = string.ascii_uppercase

  next_available_replacement_letter_index = 0
  result = ""
  prev_ent_end = 0
  entities_dict = {}  # TODO: detect any pre-existing anonymous entities like Person A, Person B in the input text and reserve these letters in the dict so that they are not reused
  reserved_replacement_letter_indexes = set()


  active_replacements = ""
  if anonymise_names:
    active_replacements += "Person|Group|Building|Organisation|Area|Location|Event|Language"
  if anonymise_names and anonymise_numbers:
    active_replacements += "|"
  if anonymise_numbers:
    active_replacements += "Money Amount|Quantity|Number"

  if len(active_replacements) > 0:

    # TODO: match also strings like "Person 123"
    re_matches = re.findall(r"(^|\s)(" + active_replacements + ")(\s+)([" + re.escape(letters) + "])(\s|:|$)", user_input)

    for re_match in re_matches:

      replacement = re_match[2]
      space = re_match[3]
      letter = re_match[4]

      replacement_letter_index = ord(letter) - ord("A")
      reserved_replacement_letter_indexes.add(replacement_letter_index)

      entities_dict[replacement + " " + letter] = replacement_letter_index  # use space as separator to normalise the dictionary keys so that same entity with different space formats gets same replacement
      # entities_dict[replacement + space + letter] = replacement_letter_index

    #/ for re_match in re_matches:

  #/ if len(active_replacements) > 0:


  for phase in range(0, 2): # two phases: 1) counting unique entities, 2) replacing them
    for word in entities.ents:

      text_original = word.text
      label = word.label_
      start_char = word.start_char
      end_char = word.end_char

      text_normalised = re.sub(r"\s+", " ", text_original) # normalise the dictionary keys so that same entity with different space formats gets same replacement

      if phase == 0 and text_normalised in entities_dict: # Spacy detects texts like "Location C" as entities
        continue

      if label == "PERSON":
        replacement = "Person" if anonymise_names else None
      elif label == "NORP":
        replacement = "Group" if anonymise_names else None
      elif label == "FAC":
        replacement = "Building" if anonymise_names else None
      elif label == "ORG":
        replacement = "Organisation" if anonymise_names else None
      elif label == "GPE":
        replacement = "Area" if anonymise_names else None
      elif label == "LOC":
        replacement = "Location" if anonymise_names else None
      elif label == "PRODUCT":
        replacement = None  # "Product"
      elif label == "EVENT":
        replacement = "Event" if anonymise_names else None
      elif label == "WORK_OF_ART":
        replacement = None  # "Work of art"
      elif label == "LAW":
        replacement = None  # "Law"
      elif label == "LANGUAGE":
        replacement = "Language" if anonymise_names else None
      elif label == "DATE":
        replacement = None  # "Calendar Date" if anonymise_numbers else None   # TODO: recognise only calendar dates, not phrases like "a big day", "today", etc
      elif label == "TIME":
        replacement = None  # "Time"
      elif label == "PERCENT":
        replacement = None  # "Percent"
      elif label == "MONEY":
        replacement = "Money Amount" if anonymise_numbers else None
      elif label == "QUANTITY":
        replacement = "Quantity" if anonymise_numbers else None
      elif label == "ORDINAL":
        replacement = None  # "Ordinal"
      elif label == "CARDINAL":
        replacement = (
                        "Number" if 
                        anonymise_numbers 
                        and len(text_normalised) > 2  #    # do not anonymise short number since they are likely ordinals too
                        and re.search(r"(\d|\s)", text_normalised) is not None   # if it is a one-word textual representation of a number then do not normalise it. It might be phrase like "one-sided" etc, which is actually not a number
                        else None
                      )
      else:
        replacement = None


      if phase == 1:
        result += user_input[prev_ent_end:start_char]
        prev_ent_end = end_char


      if replacement is None:

        if phase == 1:
          result += text_original 

      else:

        if phase == 0:

          if text_normalised not in entities_dict:

            while next_available_replacement_letter_index in reserved_replacement_letter_indexes:
              next_available_replacement_letter_index += 1

            replacement_letter_index = next_available_replacement_letter_index

            entities_dict[text_normalised] = replacement_letter_index
            reserved_replacement_letter_indexes.add(replacement_letter_index)

          #/ if text_normalised not in entities_dict:

        else:   #/ if phase == 0:

          replacement_letter_index = entities_dict[text_normalised]

          if len(reserved_replacement_letter_indexes) <= len(letters):
            replacement_letter = letters[replacement_letter_index]
          else:
            replacement_letter = str(replacement_letter_index + 1)  # use numeric names if there are too many entities in input to use letters

          result += replacement + " " + replacement_letter

        #/ if phase == 0:

      #/ if replacement is None:

    #/ for word in entities.ents:
  #/ for phase in range(0, 2):


  result += user_input[prev_ent_end:]


  return result

#/ def anonymise_uncached()


async def anonymise(config, user_input, anonymise_names, anonymise_numbers, ner_model, enable_cache = True):

  # Spacy's NER is not able to see names separated by multiple spaces as a single name. Newlines in names are fortunately ok though. Tabs are ok too, though they will still be replaced in the following regex.
  # Replace spaces before caching so that changes in spacing do not require cache update
  user_input = re.sub(r"[^\S\r\n]+", " ", user_input)    # replace all repeating whitespace which is not newline with a single space - https://stackoverflow.com/questions/3469080/match-whitespace-but-not-newlines


  encrypt_cache_data = config["encrypt_cache_data"]

  if encrypt_cache_data:
    result = await async_cached_encrypted(1 if enable_cache else None, anonymise_uncached, user_input, anonymise_names, anonymise_numbers, ner_model)
  else:
    result = await async_cached(1 if enable_cache else None, anonymise_uncached, user_input, anonymise_names, anonymise_numbers, ner_model)

  return result

#/ async def anonymise():


def render_highlights_uncached(user_input, expression_dicts):

  safeprint("Loading Spacy HTML renderer...")
  from spacy import displacy    # load it only when rendering is requested, since this package loads slowly

  highlights_html = displacy.render( 
          {
              "text": user_input,
              "ents": [
                        {
                          "start": entry["start_char"], 
                          "end": entry["end_char"], 
                          "label": ", ".join(entry["labels"])
                        } 
                        for entry 
                        in expression_dicts
                      ],
              "title": None 
          }, 
          style="ent", manual=True
        )

  return highlights_html

#/ def render_highlights_uncached():

async def render_highlights(config, user_input, expression_dicts, enable_cache = True):

  encrypt_cache_data = config["encrypt_cache_data"]

  if encrypt_cache_data:
    result = await async_cached_encrypted(1 if enable_cache else None, render_highlights_uncached, user_input, expression_dicts)
  else:
    result = await async_cached(1 if enable_cache else None, render_highlights_uncached, user_input, expression_dicts)

  return result

#/ async def render_highlights():


def parse_labels(all_labels_as_text):

  labels_list = []
  lines = all_labels_as_text.splitlines(keepends=False)
  for line in lines:

    line = line.strip()
    if line[0] == "-":
      line = line[1:].strip()

    line = sanitise_input(line)
    line = re.sub(r"[.,:;]+", "/", line).strip()  # remove punctuation from labels

    if len(line) == 0:
      continue

    labels_list.append(line)

  #/ for line in all_labels_as_text.splitlines(keepends=False):

  all_labels_as_text = "\n".join("- " + x for x in labels_list)
  # labels_list.sort()


  return (labels_list, all_labels_as_text)

#/ def parse_labels():


async def recogniser(do_open_ended_analysis = None, do_closed_ended_analysis = None, extract_message_indexes = None, argv = None):


  argv = argv if argv else sys.argv


  config = get_config()

  if do_open_ended_analysis is None:
    do_open_ended_analysis = config["do_open_ended_analysis"]
  if do_closed_ended_analysis is None:
    do_closed_ended_analysis = config["do_closed_ended_analysis"]
  if extract_message_indexes is None:
    extract_message_indexes = config["extract_message_indexes"]

  gpt_model = config["gpt_model"]
  gpt_timeout = config["gpt_timeout"]  # TODO: into run_llm_analysis_uncached()


  labels_filename = argv[3] if len(argv) > 3 else None
  if labels_filename:
    labels_filename = os.path.join("..", labels_filename)   # the applications default data location is in folder "data", but in case of user provided files lets expect the files in the same folder than the main script
  else:
    labels_filename = "default_labels.txt"


  ignored_labels_filename = argv[4] if len(argv) > 4 else None
  if ignored_labels_filename:
    ignored_labels_filename = os.path.join("..", ignored_labels_filename)   # the applications default data location is in folder "data", but in case of user provided files lets expect the files in the same folder than the main script
  else:
    ignored_labels_filename = "ignored_labels.txt"


  closed_ended_system_instruction = (await read_txt("closed_ended_system_instruction.txt", quiet = True)).lstrip()   # NB! use .lstrip() here so that the user input can be appended with newlines still between the instruction and user input
  open_ended_system_instruction = (await read_txt("open_ended_system_instruction.txt", quiet = True)).lstrip()   # NB! use .lstrip() here so that the user input can be appended with newlines still between the instruction and user input
  extract_names_of_participants_system_instruction = (await read_txt("extract_names_of_participants_system_instruction.txt", quiet = True)).lstrip()   # NB! use .lstrip() here so that the user input can be appended with newlines still between the instruction and user input
  all_labels_as_text = (await read_txt(labels_filename, quiet = True)).strip()
  all_ignored_labels_as_text = (await read_txt(ignored_labels_filename, quiet = True)).strip()
  continuation_request = (await read_txt("continuation_request.txt", quiet = True)).strip()


  closed_ended_system_instruction_with_labels = closed_ended_system_instruction.replace("%labels%", all_labels_as_text)



  # read user input
  input_filename = argv[1] if len(argv) > 1 else None
  if input_filename:
    input_filename = os.path.join("..", input_filename)   # the applications default data location is in folder "data", but in case of user provided files lets expect the files in the same folder than the main script
    using_user_input_filename = True
  else:    
    input_filename = "test_input.txt"
    using_user_input_filename = False

  # format user input
  user_input = (await read_txt(input_filename, quiet = True)).strip()
  user_input = remove_comments(user_input) # TODO: config flag


  anonymise_names = config.get("anonymise_names")
  anonymise_numbers = config.get("anonymise_numbers")
  ner_model = config.get("named_entity_recognition_model")

  if anonymise_names or anonymise_numbers:
    user_input = await anonymise(config, user_input, anonymise_names, anonymise_numbers, ner_model)


  # sanitise user input since []{} have special meaning in the output parsing
  user_input = sanitise_input(user_input)



  # parse labels    # TODO: functionality for adding comments to the labels file which will be not sent to LLM
  (labels_list, all_labels_as_text) = parse_labels(all_labels_as_text)
  (ignored_labels_list, all_ignored_labels_as_text) = parse_labels(all_ignored_labels_as_text)



  # call the analysis function

  if do_open_ended_analysis:

    messages = [
      {"role": "system", "content": open_ended_system_instruction},
      {"role": "user", "content": user_input},
    ]

    # TODO: add temperature parameter

    open_ended_response = await run_llm_analysis(config, gpt_model, gpt_timeout, messages, continuation_request)

  else: #/ if do_open_ended_analysis:

    open_ended_response = None
  


  if do_closed_ended_analysis:

    messages = [
      {"role": "system", "content": closed_ended_system_instruction_with_labels},
      {"role": "user", "content": user_input},
    ]

    # TODO: add temperature parameter

    closed_ended_response = await run_llm_analysis(config, gpt_model, gpt_timeout, messages, continuation_request)


    # parse the closed ended response by extracting persons, citations, and labels

    # TODO: Sometimes GPT mixes up the person names in the citations. Ensure that such incorrectly assigned citations are ignored or properly re-assigned in this script.

    expressions_tuples = []
    detected_persons = set()
    unexpected_labels = set()

    if extract_message_indexes:   # TODO

      messages = [
        {"role": "system", "content": extract_names_of_participants_system_instruction},
        {"role": "user", "content": user_input},
      ]

      names_of_participants_response = await run_llm_analysis(config, gpt_model, gpt_timeout, messages, continuation_request)

      # Try to detect persons from the input text. This is necessary for preserving proper message indexing in the output in case some person is not cited by LLM at all.
      re_matches = re.findall(r"[\r\n]+\[?([^\]\n]*)\]?", "\n" + names_of_participants_response)
      for re_match in re_matches:

        detected_persons.add(re_match)

      #/ for re_match in re_matches:
    #/ if extract_message_indexes:

    # Process LLM response
    re_matches = re.findall(r"[\r\n]+\[(.*)\]:(.*)\{(.*)\}", "\n" + closed_ended_response)
    for re_match in re_matches:

      (person, citation, labels) = re_match
      citation = citation.strip()
      if citation[-1] == "-":   # remove the dash between the citation and labels. Note that ChatGPT may omit this dash even if it is present in the instruction
        citation = citation[0:-1].strip()

      detected_persons.add(person)


      labels = [x.strip() for x in labels.split(",")]

      filtered_labels = []
      for label in labels:  # create debug info about non-requested labels

        if label in ignored_labels_list:
          continue

        if label not in labels_list:

          unexpected_labels.add(label)

          if config.get("keep_unexpected_labels"):
            labels_list.append(label)
          else:
            continue  # throw away any non-requested labels

        #/ if label not in labels_list:

        filtered_labels.append(label)

      #/ for label in labels:

      labels = filtered_labels
      
      if len(labels) == 0:
        continue

      expressions_tuples.append((person, citation, labels), )

    #/ for re_match in re_matches:


    labels_list.sort()


    # split input text into messages, compute the locations of messages

    person_messages = {person: [] for person in detected_persons}
    overall_message_indexes = {person: {} for person in detected_persons}  
    start_char_to_person_message_index_dict = {}
    person_message_spans = {person: [] for person in detected_persons}

    split_messages_by = config["split_messages_by"]
    split_messages_by_newline = (split_messages_by == "")

    for person in detected_persons:

      # using finditer() since it provides match.start() in the results
      if split_messages_by_newline:
        p = re.compile(r"[\r\n]+" + re.escape(person) + r":(.*)")
        re_matches = p.finditer("\n" + user_input)    # TODO: ensure that ":" character inside messages does not mess the analysis up
      else:
        p = re.compile(r"[\r\n]+" + re.escape(person) + r":(.*?)[\r\n]+" + re.escape(split_messages_by), re.DOTALL)
        re_matches = p.finditer("\n" + user_input + "\n" + split_messages_by)    # TODO: ensure that ":" character inside messages does not mess the analysis up

      for re_match in re_matches:

        message = re_match.group(1)
        
        message = message.rstrip()

        len_before_lstrip = len(message)
        message = message.lstrip()
        num_stripped_leading_chars = len_before_lstrip - len(message)

        start_char = re_match.start(1) + num_stripped_leading_chars - 1    # -1 for the prepended \n
        end_char = start_char + len(message)

        start_char_to_person_message_index_dict[start_char] = (person, len(person_messages[person]))

        person_messages[person].append(message)
        person_message_spans[person].append((start_char, end_char), )

      #/ for re_match in re_matches:
    #/ for person in detected_persons:


    # sort message indexes by start_char
    start_char_to_person_message_index_dict = OrderedDict(sorted(start_char_to_person_message_index_dict.items()))

    # compute overall message index for each person's message index
    for overall_message_index, entry in enumerate(start_char_to_person_message_index_dict.values()):
      (person, person_message_index) = entry
      overall_message_indexes[person][person_message_index] = overall_message_index


    # compute expression locations
    totals = defaultdict(lambda: OrderedDict([(label, 0) for label in labels_list]))    # defaultdict: do not report persons and labels which are not detected  # need to initialise the inner dict to preserve proper label ordering
    expression_dicts = []
    # already_labelled_message_indexes = set()
    already_labelled_message_parts = {}

    ignore_incorrectly_assigned_citations = config["ignore_incorrectly_assigned_citations"]
    allow_multiple_citations_per_message = config["allow_multiple_citations_per_message"]

    for tuple_index, expressions_tuple in enumerate(expressions_tuples):  # tuple_index is for debugging

      (person, citation, labels) = expressions_tuple
      

      # TODO: use combinatorial optimisation to do the matching with original text positions in order to ensure that repeated similar expressions get properly located as well

      # find nearest actual message and verify that it was expressed by the same person as in LLM's citation
      nearest_message_similarity = 0
      nearest_message_is_partial_match = None
      nearest_person = None
      nearest_message = None 
      nearest_person_message_index = None

      for person2 in detected_persons:

        curr_person_messages = person_messages.get(person2)
        if curr_person_messages is None or len(curr_person_messages) == 0:
          continue  # TODO: log error


        # * Simple Ratio: It computes the standard Levenshtein distance similarity ratio between two sequences.
        #
        # * Partial Ratio: It computes the partial Levenshtein distance similarity ratio between two sequences, by finding the best matching substring of the longer sequence and comparing it to the shorter sequence.
        #
        # * Token Sort Ratio: It computes the Levenshtein distance similarity ratio between two sequences after tokenizing them by whitespace and sorting them alphabetically.
        #
        # * Token Set Ratio: It computes the Levenshtein distance similarity ratio between two sequences after tokenizing them by whitespace and performing a set operation on them (union, intersection, difference).
        #
        # * Partial Token Sort Ratio: It computes the partial Levenshtein distance similarity ratio between two sequences after tokenizing them by whitespace and sorting them alphabetically, by finding the best matching substring of the longer sequence and comparing it to the shorter sequence.
        # 
        #You can also use the process module to extract the best matches from a list of choices, using any of the above scorers or a custom one.

        # TODO: use the process module to choose best partial ratio match with least extra characters in the original text.

        match = rapidfuzz.process.extractOne(citation, curr_person_messages, scorer=rapidfuzz.fuzz.partial_ratio) # partial ratio means that if the original message has text in the beginning or end around the citation then that is not considered during scoring of the match
        (person2_nearest_message, similarity, person2_message_index) = match
        similarity_is_partial_match = True

        if len(citation) > len(person2_nearest_message):  # if the citation is longer than partial match then use simple ratio matching instead
          match = rapidfuzz.process.extractOne(citation, curr_person_messages, scorer=rapidfuzz.fuzz.ratio) 
          (person2_nearest_message, similarity, person2_message_index) = match
          similarity_is_partial_match = False


        if (
          similarity > nearest_message_similarity 
          or (  # if previous nearest message was partial match then prefer simple match with same score
            similarity == nearest_message_similarity 
            and nearest_message_is_partial_match
            and not similarity_is_partial_match 
          )
          or (  # if multiple original messages have same similarity score then prefer the message with a person that was assigned by LLM
            similarity == nearest_message_similarity 
            and similarity_is_partial_match == nearest_message_is_partial_match   # both are partial matches or both are simple matches
            and person2 == person
          )  
        ):
          nearest_message_similarity = similarity
          nearest_message_is_partial_match = similarity_is_partial_match
          nearest_person = person2
          nearest_message = person2_nearest_message
          nearest_person_message_index = person2_message_index

      #/ for person2 in persons:


      if nearest_person != person:  # incorrectly assigned citation 
        if ignore_incorrectly_assigned_citations:   
          continue
        else:
          person = nearest_person    


      if not allow_multiple_citations_per_message:
        if nearest_message in already_labelled_message_parts: # TODO: if LLM labels the message parts separately, then label them separately in HTML output as well
          already_labelled_message_parts[nearest_message]["labels"] += labels
          continue  # if repeated citations have different labels, take labels from all of citations
        # else:
        #   already_labelled_message_parts.add(nearest_message)
      #/ if not allow_multiple_citations_per_message:


      # init with fallback values for case precise citation is not found
      citation_in_nearest_message = nearest_message
      start_char = person_message_spans[person][nearest_person_message_index][0]
      end_char = start_char + len(nearest_message)


      if allow_multiple_citations_per_message:

        # TODO: cache results of this loop in cases it runs longer than n milliseconds

        max_l_dist = None
        try: # NB! try needs to be outside of the time_limit context

          citation_lookup_time_limit = config["citation_lookup_time_limit"]

          outer_time_limit = citation_lookup_time_limit
          with time_limit(outer_time_limit, msg = "find_near_matches outer"):

            for max_l_dist in range(0, min(len(citation), len(nearest_message))): # len(shortest_text)-1 is maximum reasonable distance. After that empty strings will match too   # TODO: apply time limit to this loop  

              # NB! need to apply time limit to this function since in some cases it hangs
              #try: # NB! try needs to be outside of the time_limit context
              #  inner_time_limit = citation_lookup_time_limit
              #  with time_limit(inner_time_limit if inner_time_limit < outer_time_limit else None, msg = "find_near_matches inner"): 
              #    matches = find_near_matches(citation, nearest_message, max_l_dist=max_l_dist)  
              #except TimeoutError:
              #  safeprint(f"Encountered an inner time limit during detection of citation location. tuple_index={tuple_index} max_l_dist={max_l_dist}")
              #  matches = []
              matches = find_near_matches(citation, nearest_message, max_l_dist=max_l_dist)  
          
              if len(matches) > 0:

                start_char = person_message_spans[person][nearest_person_message_index][0] + matches[0].start
                end_char = start_char + matches[0].end - matches[0].start
                citation_in_nearest_message = matches[0].matched

                # for some reason the fuzzy matching keeps newlines in the nearest match even when they are not present in the citation. Lets remove them.

                len_before_strip = len(citation_in_nearest_message)
                citation_in_nearest_message = citation_in_nearest_message.lstrip()
                start_char += len_before_strip - len(citation_in_nearest_message)

                len_before_strip = len(citation_in_nearest_message)
                citation_in_nearest_message = citation_in_nearest_message.rstrip()
                end_char -= len_before_strip - len(citation_in_nearest_message)

                break

              #/ if len(matches) > 0:
            #/ for max_l_dist in range(0, len(citation)):

          #/ with time_limit(0.1):
        except TimeoutError:
          safeprint(f"Encountered a time limit during detection of citation location. tuple_index={tuple_index} max_l_dist={max_l_dist}. Skipping citation \"{citation}\". Is a similar line formatted properly in the input file?")
          continue # Skip this citation from the output, do not even use the whole message. It is likely that the citation does not meaningfully match the content of nearest_message variable.

      #/ if allow_multiple_citations_per_message


      entry = {
        "person": person,
        "start_char": start_char,
        "end_char": end_char,
        # "start_message": overall_message_index, 
        # "end_message": overall_message_index,   
        "text": citation_in_nearest_message,   # use original text not ChatGPT citation here
        "labels": labels,
      }

      if extract_message_indexes:

        # nearest_person_message_index = person_messages[person].index(nearest_message)
        overall_message_index = overall_message_indexes[person][nearest_person_message_index]  

        entry.update({
          "start_message": overall_message_index, 
          "end_message": overall_message_index,   
        })
      #/ if extract_message_indexes:


      if not allow_multiple_citations_per_message:
        already_labelled_message_parts[nearest_message] = entry

      expression_dicts.append(entry)
      
    #/ for expressions_tuple in expressions_tuples:


    # need to sort since ChatGPT sometimes does not cite the expressions in the order they appear originally
    expression_dicts.sort(key = lambda entry: entry["start_char"])

    # create new tuples list since the original list is potentially unordered
    # expressions_tuples_out = [(entry["person"], entry["text"], entry["labels"]) for entry in expression_dicts]


    qqq = True  # for debugging

  else:   #/ if do_closed_ended_analysis:

    closed_ended_response = None
    totals = None
    expression_dicts = None
    # expressions_tuples = None
    unexpected_labels = None

  #/ if do_closed_ended_analysis:


  for entry in expression_dicts:

    entry["labels"] = list(set(entry["labels"]))  # keep unique labels per entry
    entry["labels"].sort()

    person = entry["person"]
    labels = entry["labels"]

    for label in labels:
      totals[person][label] += 1

  #/ for entry in expression_dicts:


  # cleanup zero valued counts in totals
  for (person, person_counts) in totals.items():
    totals[person] = OrderedDict([(key, value) for (key, value) in person_counts.items() if value > 0])


  unexpected_labels = list(unexpected_labels)   # convert set() to list() for enabling conversion into json
  unexpected_labels.sort()

  analysis_response = {

    "error_code": 0,  # TODO
    "error_msg": "",  # TODO

    "sanitised_text": user_input,
    "expressions": expression_dicts,
    # "expressions_tuples": expressions_tuples_out,
    "counts": totals,
    "unexpected_labels": unexpected_labels,
    "raw_expressions_labeling_response": closed_ended_response,
    "qualitative_evaluation": open_ended_response   # TODO: split person A and person B from qualitative description into separate dictionary fields
  }

  response_json = json_tricks.dumps(analysis_response, indent=2)   # json_tricks preserves dictionary orderings

  response_filename = argv[2] if len(argv) > 2 else None
  if response_filename:
    response_filename = os.path.join("..", response_filename)   # the applications default data location is in folder "data", but in case of user provided files lets expect the files in the same folder than the main script
  else: 
    response_filename = os.path.splitext(input_filename)[0] + "_evaluation.json" if using_user_input_filename else "test_evaluation.json"

  await save_txt(response_filename, response_json, quiet = True, make_backup = True, append = False)



  safeprint("Analysis done.")

  

  render_output = config.get("render_output")   
  if render_output:


    chart_type = config.get("chart_type")


    title = "Manipulative Expression Recognition (MER)"


    import pygal
    import pygal.style
  
  
    # creating the chart object
    style = pygal.style.DefaultStyle(
      foreground = "rgba(0, 0, 0, .87)",              # dimension labels, plot line legend, and numbers
      foreground_strong = "rgba(128, 128, 128, 1)",   # title and radial lines
      # foreground_subtle = "rgba(128, 255, 128, .54)", # ?
      guide_stroke_color = "#404040",                 # circular lines
      major_guide_stroke_color = "#808080",           # major circular lines
      stroke_width = 2,                               # plot line width
    )


    if chart_type == "radar":
      chart = pygal.Radar(style=style, order_min=0)   # order_min specifies scale step in log10
      reverse_labels_order = True
      shift_labels_order_left = True
    elif chart_type == "vbar":
      chart = pygal.Bar(style=style, order_min=0)   # order_min specifies scale step in log10
      reverse_labels_order = False
      shift_labels_order_left = False
    elif chart_type == "hbar":
      chart = pygal.HorizontalBar(style=style, order_min=0)   # order_min specifies scale step in log10
      reverse_labels_order = True
      shift_labels_order_left = False
    else:
      chart = None
      reverse_labels_order = False
      shift_labels_order_left = False
        

    # keep only labels which have nonzero values for at least one person
    nonzero_labels_list = []  # this variable needs to be computed even when chart is not rendered, since if the nonzero_labels_list is empty then a message is shown that no manipulation was detected
    if True:
      for label in labels_list:
        for (person, person_counts) in totals.items():
          count = person_counts.get(label, 0)
          if count > 0:
            nonzero_labels_list.append(label)
            break   # go to next label
        #/ for (person, person_counts) in totals.items():
      #/ for label in labels_list:

  
    if chart:

      x_labels = list(nonzero_labels_list) # make copy since it may be reversed
      if reverse_labels_order:
        x_labels.reverse()
      if shift_labels_order_left:
        x_labels = rotate_list(x_labels, -1)  # rotate list left by one so that the first label appear at 12:00 on the radar chart

      chart.title = title      
      chart.x_labels = x_labels

      # series_dict = {}
      if True:
        for (person, person_counts) in totals.items():
          series = [person_counts.get(label, 0) for label in x_labels]
          chart.add(person, series)
          # series_dict[person] = series

      # for (person, series) in series_dict.items():
      #   chart.add(person, series)
  

      svg = chart.render()
      # chart.render_to_png(render_to_png='chart.png')


      #response_svg_filename = argv[5] if len(argv) > 5 else None
      #if response_svg_filename:
      #  response_svg_filename = os.path.join("..", response_svg_filename)   # the applications default data location is in folder "data", but in case of user provided files lets expect the files in the same folder than the main script
      #else: 
      response_svg_filename = os.path.splitext(response_filename)[0] + ".svg" if using_user_input_filename else "test_evaluation.svg"

      await save_raw(response_svg_filename, svg, quiet = True, make_backup = True, append = False)

    #/ if chart:


    import html
    import urllib.parse


    #response_html_filename = argv[4] if len(argv) > 4 else None
    #if response_html_filename:
    #  response_html_filename = os.path.join("..", response_html_filename)   # the applications default data location is in folder "data", but in case of user provided files lets expect the files in the same folder than the main script
    #else: 
    response_html_filename = os.path.splitext(response_filename)[0] + ".html" if using_user_input_filename else "test_evaluation.html"


    highlights_html = await render_highlights(config, user_input, expression_dicts)


    def get_full_html(for_pdfkit = False):

      result = (
              '<html>'
              + '\n<head>'
              + '\n<meta charset="utf-8">'  # needed for pdfkit
              + '\n<title>' + html.escape(title) + '</title>'
              + """\n<style>
                  .entities {
                    line-height: 1.5 !important;
                  }
                  mark {
                    line-height: 2 !important;
                    background: yellow !important;
                  }
                  mark span {
                    background: orange !important;
                    padding: 0.5em;
                  }
                  .graph object, .graph svg, .graph img {
                    max-height: 75vh;
                  }
                  .entity {
                    padding-top: 0.325em !important;
                  }
                  mark span {
                    vertical-align: initial !important;   /* needed for pdfkit */
                  }
                </style>""" 
              + '\n</head>'
              + '\n<body>'
              + (                
                  (
                    (                    
                      ('\n<div class="graph">' + svg.decode('utf8', 'ignore').replace('<svg', '<svg width="1000" height="750"') + '</div>')  # this will result in a proportionally scaled image
                      # ('\n<div class="graph"><img width="1000" height="750" src="data:image/svg+xml;base64,' + base64.b64encode(svg).decode('utf8', 'ignore') + '" /></div>')  # this would result in a non-proportionally scaled image
                      if for_pdfkit else    # pdfkit does not support linked images, the image data needs to be embedded. Also pdfkit requires the image dimensions to be specified.
                      (
                        '\n<div class="graph"><object data="'  # Using <object> tag will result in an interactive graph. Embdded svg tag would result in non-interactive graph.
                        + urllib.parse.quote_plus(
                            os.path.relpath(    # get relative path of SVG as compared to HTML file
                              response_svg_filename, 
                              os.path.dirname(response_html_filename)
                            ).replace("\\", "/"),   # change dir slashes to url slashes format
                            safe="/"  # do not encode url slashes
                          ) 
                        + '" type="image/svg+xml"></object></div>'
                      )
                    )
                    if chart else
                    ''
                  ) 
                  if len(nonzero_labels_list) > 0 else                 
                  '\n<div style="font: bold 1em Arial;">No manipulative expressions detected.</div>\n<br><br><br>'
                )
              + '\n<div style="font: bold 1em Arial;">Qualitative summary:</div><br>'
              + '\n<div style="font: 1em Arial;">' 
              + '\n' + open_ended_response 
              + '\n</div>'
              + '\n<br><br><br>'
              + '\n<div style="font: bold 1em Arial;">Labelled input:</div><br>'
              + '\n<div style="font: 1em Arial;">' 
              + '\n' + highlights_html 
              + '\n</div>\n</body>\n</html>'
            )   #/ result = (

      return result

    #/ def get_html():

    output_html = get_full_html(for_pdfkit = False)

    await save_txt(response_html_filename, output_html, quiet = True, make_backup = True, append = False)



    create_pdf = config.get("create_pdf") 
    if create_pdf:

      #try:
      #  import weasyprint

      #  pdf = weasyprint.HTML(string=output_html)
      #  pdf = pdf.write_pdf()
      #except Exception:

      import pdfkit

      pdfkit_html = get_full_html(for_pdfkit = True)

      try:
        pdf = pdfkit.from_string(pdfkit_html)
      except Exception as ex:  # TODO: catch a more specific exception type
        safeprint("Error creating pdf. Is wkhtmltopdf utility installed? See install_steps.txt for more info.")

        msg = str(ex) + "\n" + traceback.format_exc()
        print_exception(msg)

        pdf = None
      #/ except Exception as ex:


      if pdf is not None:

        #response_pdf_filename = argv[4] if len(argv) > 4 else None
        #if response_pdf_filename:
        #  response_pdf_filename = os.path.join("..", response_pdf_filename)   # the applications default data location is in folder "data", but in case of user provided files lets expect the files in the same folder than the main script
        #else: 
        response_pdf_filename = os.path.splitext(response_filename)[0] + ".pdf" if using_user_input_filename else "test_evaluation.pdf"

        await save_raw(response_pdf_filename, pdf, quiet = True, make_backup = True, append = False)

      #/ if pdf is not None:

    #/ create_pdf:

  #/ if render_output:
    


  return analysis_response

#/ async def main():



if __name__ == '__main__':
  loop.run_until_complete(recogniser(extract_message_indexes = None))   # extract_message_indexes = None - use config file


## Retry decorator with a delay of 6 milliseconds (0.006 seconds)
#@retry(stop=stop_after_delay(0.006), wait=wait_fixed(0.006))
#async def retry_recogniser():
    #return await recogniser(extract_message_indexes=None)

#if __name__ == '__main__':
    ## Call the retry_recogniser function with a retry mechanism and delay
    #asyncio.run(retry_recogniser())


