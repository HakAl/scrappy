Cerebras
https://inference-docs.cerebras.ai/api-reference/chat-completions

tip
We support ALL Cerebras models, just set model=cerebras/<any-model-on-cerebras> as a prefix when sending litellm requests

API Key
# env variable
os.environ['CEREBRAS_API_KEY']

Sample Usage
from litellm import completion
import os

os.environ['CEREBRAS_API_KEY'] = ""
response = completion(
    model="cerebras/llama3-70b-instruct",
    messages=[
        {
            "role": "user",
            "content": "What's the weather like in Boston today in Fahrenheit? (Write in JSON)",
        }
    ],
    max_tokens=10,
        
    # The prompt should include JSON if 'json_object' is selected; otherwise, you will get error code 400.
    response_format={ "type": "json_object" },
    seed=123,
    stop=["\n\n"],
    temperature=0.2,
    top_p=0.9,
    tool_choice="auto",
    tools=[],
    user="user",
)
print(response)


Sample Usage - Streaming
from litellm import completion
import os

os.environ['CEREBRAS_API_KEY'] = ""
response = completion(
    model="cerebras/llama3-70b-instruct",
    messages=[
        {
            "role": "user",
            "content": "What's the weather like in Boston today in Fahrenheit? (Write in JSON)",
        }
    ],
    stream=True,
    max_tokens=10,

    # The prompt should include JSON if 'json_object' is selected; otherwise, you will get error code 400.
    response_format={ "type": "json_object" }, 
    seed=123,
    stop=["\n\n"],
    temperature=0.2,
    top_p=0.9,
    tool_choice="auto",
    tools=[],
    user="user",
)

for chunk in response:
    print(chunk)


Usage with LiteLLM Proxy Server
Here's how to call a Cerebras model with the LiteLLM Proxy Server

Modify the config.yaml
model_list:
  - model_name: my-model
    litellm_params:
      model: cerebras/<your-model-name>  # add cerebras/ prefix to route as Cerebras provider
      api_key: api-key                 # api key to send your model


Start the proxy
$ litellm --config /path/to/config.yaml

Send Request to LiteLLM Proxy Server
OpenAI Python v1.0.0+
curl
import openai
client = openai.OpenAI(
    api_key="sk-1234",             # pass litellm proxy key, if you're using virtual keys
    base_url="http://0.0.0.0:4000" # litellm-proxy-base url
)

response = client.chat.completions.create(
    model="my-model",
    messages = [
        {
            "role": "user",
            "content": "what llm are you"
        }
    ],
)

print(response)


---

Github
https://github.com/marketplace/models

tip
We support ALL Github models, just set model=github/<any-model-on-github> as a prefix when sending litellm requests Ignore company prefix: meta/Llama-3.2-11B-Vision-Instruct becomes model=github/Llama-3.2-11B-Vision-Instruct

API Key
# env variable
os.environ['GITHUB_API_KEY']

Sample Usage
from litellm import completion
import os

os.environ['GITHUB_API_KEY'] = ""
response = completion(
    model="github/Llama-3.2-11B-Vision-Instruct", 
    messages=[
       {"role": "user", "content": "hello from litellm"}
   ],
)
print(response)

Sample Usage - Streaming
from litellm import completion
import os

os.environ['GITHUB_API_KEY'] = ""
response = completion(
    model="github/Llama-3.2-11B-Vision-Instruct", 
    messages=[
       {"role": "user", "content": "hello from litellm"}
   ],
    stream=True
)

for chunk in response:
    print(chunk)

Usage with LiteLLM Proxy
1. Set Github Models on config.yaml
model_list:
  - model_name: github-Llama-3.2-11B-Vision-Instruct # Model Alias to use for requests
    litellm_params:
      model: github/Llama-3.2-11B-Vision-Instruct
      api_key: "os.environ/GITHUB_API_KEY" # ensure you have `GITHUB_API_KEY` in your .env


2. Start Proxy
litellm --config config.yaml

3. Test it
Make request to litellm proxy

Curl Request
OpenAI v1.0.0+
Langchain
curl --location 'http://0.0.0.0:4000/chat/completions' \
--header 'Content-Type: application/json' \
--data ' {
      "model": "github-Llama-3.2-11B-Vision-Instruct",
      "messages": [
        {
          "role": "user",
          "content": "what llm are you"
        }
      ]
    }
'

Supported Models - ALL Github Models Supported!
We support ALL Github models, just set github/ as a prefix when sending completion requests

Model Name	Usage
llama-3.1-8b-Instant	completion(model="github/Llama-3.1-8b-Instant", messages)
Llama-3.1-70b-Versatile	completion(model="github/Llama-3.1-70b-Versatile", messages)
Llama-3.2-11B-Vision-Instruct	completion(model="github/Llama-3.2-11B-Vision-Instruct", messages)
Llama3-70b-8192	completion(model="github/Llama3-70b-8192", messages)
Llama2-70b-4096	completion(model="github/Llama2-70b-4096", messages)
Mixtral-8x7b-32768	completion(model="github/Mixtral-8x7b-32768", messages)
Phi-4	completion(model="github/Phi-4", messages)
Github - Tool / Function Calling Example
# Example dummy function hard coded to return the current weather
import json
def get_current_weather(location, unit="fahrenheit"):
    """Get the current weather in a given location"""
    if "tokyo" in location.lower():
        return json.dumps({"location": "Tokyo", "temperature": "10", "unit": "celsius"})
    elif "san francisco" in location.lower():
        return json.dumps(
            {"location": "San Francisco", "temperature": "72", "unit": "fahrenheit"}
        )
    elif "paris" in location.lower():
        return json.dumps({"location": "Paris", "temperature": "22", "unit": "celsius"})
    else:
        return json.dumps({"location": location, "temperature": "unknown"})




# Step 1: send the conversation and available functions to the model
messages = [
    {
        "role": "system",
        "content": "You are a function calling LLM that uses the data extracted from get_current_weather to answer questions about the weather in San Francisco.",
    },
    {
        "role": "user",
        "content": "What's the weather like in San Francisco?",
    },
]
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                    },
                },
                "required": ["location"],
            },
        },
    }
]
response = litellm.completion(
    model="github/Llama-3.2-11B-Vision-Instruct",
    messages=messages,
    tools=tools,
    tool_choice="auto",  # auto is default, but we'll be explicit
)
print("Response\n", response)
response_message = response.choices[0].message
tool_calls = response_message.tool_calls


# Step 2: check if the model wanted to call a function
if tool_calls:
    # Step 3: call the function
    # Note: the JSON response may not always be valid; be sure to handle errors
    available_functions = {
        "get_current_weather": get_current_weather,
    }
    messages.append(
        response_message
    )  # extend conversation with assistant's reply
    print("Response message\n", response_message)
    # Step 4: send the info for each function call and function response to the model
    for tool_call in tool_calls:
        function_name = tool_call.function.name
        function_to_call = available_functions[function_name]
        function_args = json.loads(tool_call.function.arguments)
        function_response = function_to_call(
            location=function_args.get("location"),
            unit=function_args.get("unit"),
        )
        messages.append(
            {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": function_response,
            }
        )  # extend conversation with function response
    print(f"messages: {messages}")
    second_response = litellm.completion(
        model="github/Llama-3.2-11B-Vision-Instruct", messages=messages
    )  # get a new response from the model where it can see the function response
    print("second response\n", second_response)


---


Groq
https://groq.com/

tip
We support ALL Groq models, just set model=groq/<any-model-on-groq> as a prefix when sending litellm requests

API Key
# env variable
os.environ['GROQ_API_KEY']

Sample Usage
from litellm import completion
import os

os.environ['GROQ_API_KEY'] = ""
response = completion(
    model="groq/llama3-8b-8192", 
    messages=[
       {"role": "user", "content": "hello from litellm"}
   ],
)
print(response)

Sample Usage - Streaming
from litellm import completion
import os

os.environ['GROQ_API_KEY'] = ""
response = completion(
    model="groq/llama3-8b-8192", 
    messages=[
       {"role": "user", "content": "hello from litellm"}
   ],
    stream=True
)

for chunk in response:
    print(chunk)

Usage with LiteLLM Proxy
1. Set Groq Models on config.yaml
model_list:
  - model_name: groq-llama3-8b-8192 # Model Alias to use for requests
    litellm_params:
      model: groq/llama3-8b-8192
      api_key: "os.environ/GROQ_API_KEY" # ensure you have `GROQ_API_KEY` in your .env

2. Start Proxy
litellm --config config.yaml

3. Test it
Make request to litellm proxy

Curl Request
OpenAI v1.0.0+
Langchain
curl --location 'http://0.0.0.0:4000/chat/completions' \
--header 'Content-Type: application/json' \
--data ' {
      "model": "groq-llama3-8b-8192",
      "messages": [
        {
          "role": "user",
          "content": "what llm are you"
        }
      ]
    }
'

Supported Models - ALL Groq Models Supported!
We support ALL Groq models, just set groq/ as a prefix when sending completion requests

Model Name	Usage
llama-3.1-8b-instant	completion(model="groq/llama-3.1-8b-instant", messages)
llama-3.1-70b-versatile	completion(model="groq/llama-3.1-70b-versatile", messages)
llama3-8b-8192	completion(model="groq/llama3-8b-8192", messages)
llama3-70b-8192	completion(model="groq/llama3-70b-8192", messages)
llama2-70b-4096	completion(model="groq/llama2-70b-4096", messages)
mixtral-8x7b-32768	completion(model="groq/mixtral-8x7b-32768", messages)
gemma-7b-it	completion(model="groq/gemma-7b-it", messages)
moonshotai/kimi-k2-instruct	completion(model="groq/moonshotai/kimi-k2-instruct", messages)
qwen3-32b	completion(model="groq/qwen/qwen3-32b", messages)
Groq - Tool / Function Calling Example
# Example dummy function hard coded to return the current weather
import json
def get_current_weather(location, unit="fahrenheit"):
    """Get the current weather in a given location"""
    if "tokyo" in location.lower():
        return json.dumps({"location": "Tokyo", "temperature": "10", "unit": "celsius"})
    elif "san francisco" in location.lower():
        return json.dumps(
            {"location": "San Francisco", "temperature": "72", "unit": "fahrenheit"}
        )
    elif "paris" in location.lower():
        return json.dumps({"location": "Paris", "temperature": "22", "unit": "celsius"})
    else:
        return json.dumps({"location": location, "temperature": "unknown"})




# Step 1: send the conversation and available functions to the model
messages = [
    {
        "role": "system",
        "content": "You are a function calling LLM that uses the data extracted from get_current_weather to answer questions about the weather in San Francisco.",
    },
    {
        "role": "user",
        "content": "What's the weather like in San Francisco?",
    },
]
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                    },
                },
                "required": ["location"],
            },
        },
    }
]
response = litellm.completion(
    model="groq/llama3-8b-8192",
    messages=messages,
    tools=tools,
    tool_choice="auto",  # auto is default, but we'll be explicit
)
print("Response\n", response)
response_message = response.choices[0].message
tool_calls = response_message.tool_calls


# Step 2: check if the model wanted to call a function
if tool_calls:
    # Step 3: call the function
    # Note: the JSON response may not always be valid; be sure to handle errors
    available_functions = {
        "get_current_weather": get_current_weather,
    }
    messages.append(
        response_message
    )  # extend conversation with assistant's reply
    print("Response message\n", response_message)
    # Step 4: send the info for each function call and function response to the model
    for tool_call in tool_calls:
        function_name = tool_call.function.name
        function_to_call = available_functions[function_name]
        function_args = json.loads(tool_call.function.arguments)
        function_response = function_to_call(
            location=function_args.get("location"),
            unit=function_args.get("unit"),
        )
        messages.append(
            {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": function_response,
            }
        )  # extend conversation with function response
    print(f"messages: {messages}")
    second_response = litellm.completion(
        model="groq/llama3-8b-8192", messages=messages
    )  # get a new response from the model where it can see the function response
    print("second response\n", second_response)


Groq - Vision Example
Select Groq models support vision. Check out their model list for more details.

SDK
PROXY
from litellm import completion

import os 
from litellm import completion

os.environ["GROQ_API_KEY"] = "your-api-key"

# openai call
response = completion(
    model = "groq/llama-3.2-11b-vision-preview", 
    messages=[
        {
            "role": "user",
            "content": [
                            {
                                "type": "text",
                                "text": "What’s in this image?"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                "url": "https://awsmp-logos.s3.amazonaws.com/seller-xw5kijmvmzasy/c233c9ade2ccb5491072ae232c814942.png"
                                }
                            }
                        ]
        }
    ],
)



Speech to Text - Whisper
os.environ["GROQ_API_KEY"] = ""
audio_file = open("/path/to/audio.mp3", "rb")

transcript = litellm.transcription(
    model="groq/whisper-large-v3",
    file=audio_file,
    prompt="Specify context or spelling",
    temperature=0,
    response_format="json"
)

print("response=", transcript)

---

Gemini - Google AI Studio
Property	Details
Description	Google AI Studio is a fully-managed AI development platform for building and using generative AI.
Provider Route on LiteLLM	gemini/
Provider Doc	Google AI Studio ↗
API Endpoint for Provider	https://generativelanguage.googleapis.com
Supported OpenAI Endpoints	/chat/completions, /embeddings, /completions, /videos, /images/edits
Pass-through Endpoint	Supported

API Keys
import os
os.environ["GEMINI_API_KEY"] = "your-api-key"

Sample Usage
from litellm import completion
import os

os.environ['GEMINI_API_KEY'] = ""
response = completion(
    model="gemini/gemini-pro", 
    messages=[{"role": "user", "content": "write code for saying hi from LiteLLM"}]
)

Supported OpenAI Params
temperature
top_p
max_tokens
max_completion_tokens
stream
tools
tool_choice
functions
response_format
n
stop
logprobs
frequency_penalty
modalities
reasoning_content
audio (for TTS models only)
Anthropic Params

thinking (used to set max budget tokens across anthropic/gemini models)
See Updated List

Usage - Thinking / reasoning_content
LiteLLM translates OpenAI's reasoning_effort to Gemini's thinking parameter. Code

Cost Optimization: Use reasoning_effort="none" (OpenAI standard) for significant cost savings - up to 96% cheaper. Google's docs

info
Note: Reasoning cannot be turned off on Gemini 2.5 Pro models.

Gemini 3 Models
For Gemini 3+ models (e.g., gemini-3-pro-preview), LiteLLM automatically maps reasoning_effort to the new thinking_level parameter instead of thinking_budget. The thinking_level parameter uses "low" or "high" values for better control over reasoning depth.

Image Models
Gemini image models (e.g., gemini-3-pro-image-preview, gemini-2.0-flash-exp-image-generation) do not support the thinking_level parameter. LiteLLM automatically excludes image models from receiving thinking configuration to prevent API errors.

Mapping for Gemini 2.5 and earlier models

reasoning_effort	thinking	Notes
"none"	"budget_tokens": 0, "includeThoughts": false	💰 Recommended for cost optimization - OpenAI-compatible, always 0
"disable"	"budget_tokens": DEFAULT (0), "includeThoughts": false	LiteLLM-specific, configurable via env var
"low"	"budget_tokens": 1024	
"medium"	"budget_tokens": 2048	
"high"	"budget_tokens": 4096	
Mapping for Gemini 3+ models

reasoning_effort	thinking_level	Notes
"minimal"	"low"	Minimizes latency and cost
"low"	"low"	Best for simple instruction following or chat
"medium"	"high"	Maps to high (medium not yet available)
"high"	"high"	Maximizes reasoning depth
"disable"	"low"	Cannot fully disable thinking in Gemini 3
"none"	"low"	Cannot fully disable thinking in Gemini 3
SDK
PROXY
from litellm import completion

# Cost-optimized: Use reasoning_effort="none" for best pricing
resp = completion(
    model="gemini/gemini-2.0-flash-thinking-exp-01-21",
    messages=[{"role": "user", "content": "What is the capital of France?"}],
    reasoning_effort="none",  # Up to 96% cheaper!
)

# Or use other levels: "low", "medium", "high"
resp = completion(
    model="gemini/gemini-2.5-flash-preview-04-17",
    messages=[{"role": "user", "content": "What is the capital of France?"}],
    reasoning_effort="low",
)


Gemini 3+ Models - thinking_level Parameter
For Gemini 3+ models (e.g., gemini-3-pro-preview), you can use the new thinking_level parameter directly:

SDK
PROXY
from litellm import completion

# Use thinking_level for Gemini 3 models
resp = completion(
    model="gemini/gemini-3-pro-preview",
    messages=[{"role": "user", "content": "Solve this complex math problem step by step."}],
    reasoning_effort="high",  # Options: "low" or "high"
)

# Low thinking level for faster, simpler tasks
resp = completion(
    model="gemini/gemini-3-pro-preview",
    messages=[{"role": "user", "content": "What is the weather today?"}],
    reasoning_effort="low",  # Minimizes latency and cost
)


warning
Temperature Recommendation for Gemini 3 Models

For Gemini 3 models, LiteLLM defaults temperature to 1.0 and strongly recommends keeping it at this default. Setting temperature < 1.0 can cause:

Infinite loops
Degraded reasoning performance
Failure on complex tasks
LiteLLM will automatically set temperature=1.0 if not specified for Gemini 3+ models.

Expected Response

ModelResponse(
    id='chatcmpl-c542d76d-f675-4e87-8e5f-05855f5d0f5e',
    created=1740470510,
    model='claude-3-7-sonnet-20250219',
    object='chat.completion',
    system_fingerprint=None,
    choices=[
        Choices(
            finish_reason='stop',
            index=0,
            message=Message(
                content="The capital of France is Paris.",
                role='assistant',
                tool_calls=None,
                function_call=None,
                reasoning_content='The capital of France is Paris. This is a very straightforward factual question.'
            ),
        )
    ],
    usage=Usage(
        completion_tokens=68,
        prompt_tokens=42,
        total_tokens=110,
        completion_tokens_details=None,
        prompt_tokens_details=PromptTokensDetailsWrapper(
            audio_tokens=None,
            cached_tokens=0,
            text_tokens=None,
            image_tokens=None
        ),
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0
    )
)


Pass thinking to Gemini models
You can also pass the thinking parameter to Gemini models.

This is translated to Gemini's thinkingConfig parameter.

SDK
PROXY
response = litellm.completion(
  model="gemini/gemini-2.5-flash-preview-04-17",
  messages=[{"role": "user", "content": "What is the capital of France?"}],
  thinking={"type": "enabled", "budget_tokens": 1024},
)

Text-to-Speech (TTS) Audio Output
info
LiteLLM supports Gemini TTS models that can generate audio responses using the OpenAI-compatible audio parameter format.

Supported Models
LiteLLM supports Gemini TTS models with audio capabilities (e.g. gemini-2.5-flash-preview-tts and gemini-2.5-pro-preview-tts). For the complete list of available TTS models and voices, see the official Gemini TTS documentation.

Limitations
warning
Important Limitations:

Gemini TTS models only support the pcm16 audio format
Streaming support has not been added to TTS models yet
The modalities parameter must be set to ['audio'] for TTS requests
Quick Start
SDK
PROXY
from litellm import completion
import os

os.environ['GEMINI_API_KEY'] = "your-api-key"

response = completion(
    model="gemini/gemini-2.5-flash-preview-tts",
    messages=[{"role": "user", "content": "Say hello in a friendly voice"}],
    modalities=["audio"],  # Required for TTS models
    audio={
        "voice": "Kore",
        "format": "pcm16"  # Required: must be "pcm16"
    }
)

print(response)

Advanced Usage
You can combine TTS with other Gemini features:

response = completion(
    model="gemini/gemini-2.5-pro-preview-tts",
    messages=[
        {"role": "system", "content": "You are a helpful assistant that speaks clearly."},
        {"role": "user", "content": "Explain quantum computing in simple terms"}
    ],
    modalities=["audio"],
    audio={
        "voice": "Charon",
        "format": "pcm16"
    },
    temperature=0.7,
    max_tokens=150
)


For more information about Gemini's TTS capabilities and available voices, see the official Gemini TTS documentation.

Passing Gemini Specific Params
Response schema
LiteLLM supports sending response_schema as a param for Gemini-1.5-Pro on Google AI Studio.

Response Schema

SDK
PROXY
from litellm import completion 
import json 
import os 

os.environ['GEMINI_API_KEY'] = ""

messages = [
    {
        "role": "user",
        "content": "List 5 popular cookie recipes."
    }
]

response_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "recipe_name": {
                    "type": "string",
                },
            },
            "required": ["recipe_name"],
        },
    }


completion(
    model="gemini/gemini-1.5-pro", 
    messages=messages, 
    response_format={"type": "json_object", "response_schema": response_schema} # 👈 KEY CHANGE
    )

print(json.loads(completion.choices[0].message.content))


Validate Schema

To validate the response_schema, set enforce_validation: true.

SDK
PROXY
from litellm import completion, JSONSchemaValidationError
try: 
	completion(
    model="gemini/gemini-1.5-pro", 
    messages=messages, 
    response_format={
        "type": "json_object", 
        "response_schema": response_schema,
        "enforce_validation": true # 👈 KEY CHANGE
    }
	)
except JSONSchemaValidationError as e: 
	print("Raw Response: {}".format(e.raw_response))
	raise e

LiteLLM will validate the response against the schema, and raise a JSONSchemaValidationError if the response does not match the schema.

JSONSchemaValidationError inherits from openai.APIError

Access the raw response with e.raw_response

GenerationConfig Params
To pass additional GenerationConfig params - e.g. topK, just pass it in the request body of the call, and LiteLLM will pass it straight through as a key-value pair in the request body.

See Gemini GenerationConfigParams

SDK
PROXY
from litellm import completion 
import json 
import os 

os.environ['GEMINI_API_KEY'] = ""

messages = [
    {
        "role": "user",
        "content": "List 5 popular cookie recipes."
    }
]

completion(
    model="gemini/gemini-1.5-pro", 
    messages=messages, 
    topK=1 # 👈 KEY CHANGE
)

print(json.loads(completion.choices[0].message.content))

Validate Schema

To validate the response_schema, set enforce_validation: true.

SDK
PROXY
from litellm import completion, JSONSchemaValidationError
try: 
	completion(
    model="gemini/gemini-1.5-pro", 
    messages=messages, 
    response_format={
        "type": "json_object", 
        "response_schema": response_schema,
        "enforce_validation": true # 👈 KEY CHANGE
    }
	)
except JSONSchemaValidationError as e: 
	print("Raw Response: {}".format(e.raw_response))
	raise e

Specifying Safety Settings
In certain use-cases you may need to make calls to the models and pass safety settings different from the defaults. To do so, simple pass the safety_settings argument to completion or acompletion. For example:

response = completion(
    model="gemini/gemini-pro", 
    messages=[{"role": "user", "content": "write code for saying hi from LiteLLM"}],
    safety_settings=[
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE",
        },
    ]
)

Tool Calling
from litellm import completion
import os
# set env
os.environ["GEMINI_API_KEY"] = ".."

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["location"],
            },
        },
    }
]
messages = [{"role": "user", "content": "What's the weather like in Boston today?"}]

response = completion(
    model="gemini/gemini-1.5-flash",
    messages=messages,
    tools=tools,
)
# Add any assertions, here to check response args
print(response)
assert isinstance(response.choices[0].message.tool_calls[0].function.name, str)
assert isinstance(
    response.choices[0].message.tool_calls[0].function.arguments, str
)



Google Search Tool
SDK
PROXY
from litellm import completion
import os

os.environ["GEMINI_API_KEY"] = ".."

tools = [{"googleSearch": {}}] # 👈 ADD GOOGLE SEARCH

response = completion(
    model="gemini/gemini-2.0-flash",
    messages=[{"role": "user", "content": "What is the weather in San Francisco?"}],
    tools=tools,
)

print(response)

URL Context
SDK
PROXY
from litellm import completion
import os

os.environ["GEMINI_API_KEY"] = ".."

# 👇 ADD URL CONTEXT
tools = [{"urlContext": {}}]

response = completion(
    model="gemini/gemini-2.0-flash",
    messages=[{"role": "user", "content": "Summarize this document: https://ai.google.dev/gemini-api/docs/models"}],
    tools=tools,
)

print(response)

# Access URL context metadata
url_context_metadata = response.model_extra['vertex_ai_url_context_metadata']
urlMetadata = url_context_metadata[0]['urlMetadata'][0]
print(f"Retrieved URL: {urlMetadata['retrievedUrl']}")
print(f"Retrieval Status: {urlMetadata['urlRetrievalStatus']}")


Google Search Retrieval
SDK
PROXY
from litellm import completion
import os

os.environ["GEMINI_API_KEY"] = ".."

tools = [{"googleSearch": {}}] # 👈 ADD GOOGLE SEARCH

response = completion(
    model="gemini/gemini-2.0-flash",
    messages=[{"role": "user", "content": "What is the weather in San Francisco?"}],
    tools=tools,
)

print(response)

Code Execution Tool
SDK
PROXY
from litellm import completion
import os

os.environ["GEMINI_API_KEY"] = ".."

tools = [{"codeExecution": {}}] # 👈 ADD GOOGLE SEARCH

response = completion(
    model="gemini/gemini-2.0-flash",
    messages=[{"role": "user", "content": "What is the weather in San Francisco?"}],
    tools=tools,
)

print(response)

Computer Use Tool
LiteLLM Python SDK
LiteLLM Proxy Server
from litellm import completion
import os

os.environ["GEMINI_API_KEY"] = "your-api-key"

# Computer Use tool with browser environment
tools = [
    {
        "type": "computer_use",
        "environment": "browser",  # optional: "browser" or "unspecified"
        "excluded_predefined_functions": ["drag_and_drop"]  # optional
    }
]

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "Navigate to google.com and search for 'LiteLLM'"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64,..."  # screenshot of current browser state
                }
            }
        ]
    }
]

response = completion(
    model="gemini/gemini-2.5-computer-use-preview-10-2025",
    messages=messages,
    tools=tools,
)

print(response)

# Handling tool responses with screenshots
# When the model makes a tool call, send the response back with a screenshot:
if response.choices[0].message.tool_calls:
    tool_call = response.choices[0].message.tool_calls[0]
    
    # Add assistant message with tool call
    messages.append(response.choices[0].message.model_dump())
    
    # Add tool response with screenshot
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": [
            {
                "type": "text",
                "text": '{"url": "https://example.com", "status": "completed"}'
            },
            {
                "type": "input_image",
                "image_url": "data:image/png;base64,..."  # New screenshot after action (Can send an image url as well, litellm handles the conversion)
            }
        ]
    })
    
    # Continue conversation with updated screenshot
    response = completion(
        model="gemini/gemini-2.5-computer-use-preview-10-2025",
        messages=messages,
        tools=tools,
    )


Environment Mapping
LiteLLM Input	Gemini API Value
"browser"	ENVIRONMENT_BROWSER
"unspecified"	ENVIRONMENT_UNSPECIFIED
ENVIRONMENT_BROWSER	ENVIRONMENT_BROWSER (passed through)
ENVIRONMENT_UNSPECIFIED	ENVIRONMENT_UNSPECIFIED (passed through)
Thought Signatures
Thought signatures are encrypted representations of the model's internal reasoning process for a given turn in a conversation. By passing thought signatures back to the model in subsequent requests, you provide it with the context of its previous thoughts, allowing it to build upon its reasoning and maintain a coherent line of inquiry.

Thought signatures are particularly important for multi-turn function calling scenarios where the model needs to maintain context across multiple tool invocations.

How Thought Signatures Work
Function calls with signatures: When Gemini returns a function call, it includes a thought_signature in the response
Preservation: LiteLLM automatically extracts and stores thought signatures in provider_specific_fields of tool calls
Return in conversation history: When you include the assistant's message with tool calls in subsequent requests, LiteLLM automatically preserves and returns the thought signatures to Gemini
Parallel function calls: Only the first function call in a parallel set has a thought signature
Sequential function calls: Each function call in a multi-step sequence has its own signature
Enabling Thought Signatures
To enable thought signatures, you need to enable thinking/reasoning:

SDK
PROXY
from litellm import completion

response = completion(
    model="gemini/gemini-2.5-flash",
    messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
    tools=[...],
    reasoning_effort="low",  # Enable thinking to get thought signatures
)

Multi-Turn Function Calling with Thought Signatures
When building conversation history for multi-turn function calling, you must include the thought signatures from previous responses. LiteLLM handles this automatically when you append the full assistant message to your conversation history.

OpenAI Client
cURL
from openai import OpenAI
import json

client = OpenAI(api_key="sk-1234", base_url="http://localhost:4000")

def get_current_temperature(location: str) -> dict:
    """Gets the current weather temperature for a given location."""
    return {"temperature": 30, "unit": "celsius"}

def set_thermostat_temperature(temperature: int) -> dict:
    """Sets the thermostat to a desired temperature."""
    return {"status": "success"}

get_weather_declaration = {
    "name": "get_current_temperature",
    "description": "Gets the current weather temperature for a given location.",
    "parameters": {
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"],
    },
}

set_thermostat_declaration = {
    "name": "set_thermostat_temperature",
    "description": "Sets the thermostat to a desired temperature.",
    "parameters": {
        "type": "object",
        "properties": {"temperature": {"type": "integer"}},
        "required": ["temperature"],
    },
}

# Initial request
messages = [
    {"role": "user", "content": "If it's too hot or too cold in London, set the thermostat to a comfortable level."}
]

response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=messages,
    tools=[get_weather_declaration, set_thermostat_declaration],
    reasoning_effort="low"
)

# Append the assistant's message (includes thought signatures automatically)
messages.append(response.choices[0].message)

# Execute tool calls and append results
for tool_call in response.choices[0].message.tool_calls:
    if tool_call.function.name == "get_current_temperature":
        result = get_current_temperature(**json.loads(tool_call.function.arguments))
        messages.append({
            "role": "tool",
            "content": json.dumps(result),
            "tool_call_id": tool_call.id
        })

# Second request - thought signatures are automatically preserved
response2 = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=messages,
    tools=[get_weather_declaration, set_thermostat_declaration],
    reasoning_effort="low"
)

print(response2.choices[0].message.content)


Important Notes
Automatic Handling: LiteLLM automatically extracts thought signatures from Gemini responses and preserves them when you include assistant messages in conversation history. You don't need to manually extract or manage them.

Parallel Function Calls: When the model makes parallel function calls, only the first function call will have a thought signature. Subsequent parallel calls won't have signatures.

Sequential Function Calls: In multi-step function calling scenarios, each step's first function call will have its own thought signature that must be preserved.

Required for Context: Thought signatures are essential for maintaining reasoning context across multi-turn conversations with function calling. Without them, the model may lose context of its previous reasoning.

Format: Thought signatures are stored in provider_specific_fields.thought_signature of tool calls in the response, and are automatically included when you append the assistant message to your conversation history.

Chat Completions Clients: With chat completions clients where you cannot control whether or not the previous assistant message is included as-is (ex langchain's ChatOpenAI), LiteLLM also preserves the thought signature by appending it to the tool call id (call_123__thought__<thought-signature>) and extracting it back out before sending the outbound request to Gemini.

JSON Mode
SDK
PROXY
from litellm import completion 
import json 
import os 

os.environ['GEMINI_API_KEY'] = ""

messages = [
    {
        "role": "user",
        "content": "List 5 popular cookie recipes."
    }
]



completion(
    model="gemini/gemini-1.5-pro", 
    messages=messages, 
    response_format={"type": "json_object"} # 👈 KEY CHANGE
)

print(json.loads(completion.choices[0].message.content))

Gemini-Pro-Vision
LiteLLM Supports the following image types passed in url

Images with direct links - https://storage.googleapis.com/github-repo/img/gemini/intro/landmark3.jpg
Image in local storage - ./localimage.jpeg
Image Resolution Control (Gemini 3+)
For Gemini 3+ models, LiteLLM supports per-part media resolution control using OpenAI's detail parameter. This allows you to specify different resolution levels for individual images in your request.

Supported detail values:

"low" - Maps to media_resolution: "low" (280 tokens for images, 70 tokens per frame for videos)
"high" - Maps to media_resolution: "high" (1120 tokens for images)
"auto" or None - Model decides optimal resolution (no media_resolution set)
Usage Example:

from litellm import completion

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://example.com/chart.png",
                    "detail": "high"  # High resolution for detailed chart analysis
                }
            },
            {
                "type": "text",
                "text": "Analyze this chart"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://example.com/icon.png",
                    "detail": "low"  # Low resolution for simple icon
                }
            }
        ]
    }
]

response = completion(
    model="gemini/gemini-3-pro-preview",
    messages=messages,
)

info
Per-Part Resolution: Each image in your request can have its own detail setting, allowing mixed-resolution requests (e.g., a high-res chart alongside a low-res icon). This feature is only available for Gemini 3+ models.

Sample Usage
import os
import litellm
from dotenv import load_dotenv

# Load the environment variables from .env file
load_dotenv()
os.environ["GEMINI_API_KEY"] = os.getenv('GEMINI_API_KEY')

prompt = 'Describe the image in a few sentences.'
# Note: You can pass here the URL or Path of image directly.
image_url = 'https://storage.googleapis.com/github-repo/img/gemini/intro/landmark3.jpg'

# Create the messages payload according to the documentation
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": prompt
            },
            {
                "type": "image_url",
                "image_url": {"url": image_url}
            }
        ]
    }
]

# Make the API call to Gemini model
response = litellm.completion(
    model="gemini/gemini-pro-vision",
    messages=messages,
)

# Extract the response content
content = response.get('choices', [{}])[0].get('message', {}).get('content')

# Print the result
print(content)

Usage - PDF / Videos / etc. Files
Inline Data (e.g. audio stream)
LiteLLM follows the OpenAI format and accepts sending inline data as an encoded base64 string.

The format to follow is

data:<mime_type>;base64,<encoded_data>

** LITELLM CALL **

import litellm
from pathlib import Path
import base64
import os

os.environ["GEMINI_API_KEY"] = "" 

litellm.set_verbose = True # 👈 See Raw call 

audio_bytes = Path("speech_vertex.mp3").read_bytes()
encoded_data = base64.b64encode(audio_bytes).decode("utf-8")
print("Audio Bytes = {}".format(audio_bytes))
model = "gemini/gemini-1.5-flash"
response = litellm.completion(
    model=model,
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Please summarize the audio."},
                {
                    "type": "file",
                    "file": {
                        "file_data": "data:audio/mp3;base64,{}".format(encoded_data), # 👈 SET MIME_TYPE + DATA
                    }
                },
            ],
        }
    ],
)


** Equivalent GOOGLE API CALL **

# Initialize a Gemini model appropriate for your use case.
model = genai.GenerativeModel('models/gemini-1.5-flash')

# Create the prompt.
prompt = "Please summarize the audio."

# Load the samplesmall.mp3 file into a Python Blob object containing the audio
# file's bytes and then pass the prompt and the audio to Gemini.
response = model.generate_content([
    prompt,
    {
        "mime_type": "audio/mp3",
        "data": pathlib.Path('samplesmall.mp3').read_bytes()
    }
])

# Output Gemini's response to the prompt and the inline audio.
print(response.text)

https:// file
import litellm
import os

os.environ["GEMINI_API_KEY"] = "" 

litellm.set_verbose = True # 👈 See Raw call 

model = "gemini/gemini-1.5-flash"
response = litellm.completion(
    model=model,
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Please summarize the file."},
                {
                    "type": "file",
                    "file": {
                        "file_id": "https://storage...", # 👈 SET THE IMG URL
                        "format": "application/pdf" # OPTIONAL
                    }
                },
            ],
        }
    ],
)

gs:// file
import litellm
import os

os.environ["GEMINI_API_KEY"] = "" 

litellm.set_verbose = True # 👈 See Raw call 

model = "gemini/gemini-1.5-flash"
response = litellm.completion(
    model=model,
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Please summarize the file."},
                {
                    "type": "file",
                    "file": {
                        "file_id": "gs://storage...", # 👈 SET THE IMG URL
                        "format": "application/pdf" # OPTIONAL
                    }
                },
            ],
        }
    ],
)

Chat Models
tip
We support ALL Gemini models, just set model=gemini/<any-model-on-gemini> as a prefix when sending litellm requests

Model Name	Function Call	Required OS Variables
gemini-pro	completion(model='gemini/gemini-pro', messages)	os.environ['GEMINI_API_KEY']
gemini-1.5-pro-latest	completion(model='gemini/gemini-1.5-pro-latest', messages)	os.environ['GEMINI_API_KEY']
gemini-2.0-flash	completion(model='gemini/gemini-2.0-flash', messages)	os.environ['GEMINI_API_KEY']
gemini-2.0-flash-exp	completion(model='gemini/gemini-2.0-flash-exp', messages)	os.environ['GEMINI_API_KEY']
gemini-2.0-flash-lite-preview-02-05	completion(model='gemini/gemini-2.0-flash-lite-preview-02-05', messages)	os.environ['GEMINI_API_KEY']
gemini-2.5-flash-preview-09-2025	completion(model='gemini/gemini-2.5-flash-preview-09-2025', messages)	os.environ['GEMINI_API_KEY']
gemini-2.5-flash-lite-preview-09-2025	completion(model='gemini/gemini-2.5-flash-lite-preview-09-2025', messages)	os.environ['GEMINI_API_KEY']
gemini-flash-latest	completion(model='gemini/gemini-flash-latest', messages)	os.environ['GEMINI_API_KEY']
gemini-flash-lite-latest	completion(model='gemini/gemini-flash-lite-latest', messages)	os.environ['GEMINI_API_KEY']
Context Caching
Use Google AI Studio context caching is supported by

{
    {
        "role": "system",
        "content": ...,
        "cache_control": {"type": "ephemeral"} # 👈 KEY CHANGE
    },
    ...
}

in your message content block.

Custom TTL Support
You can now specify a custom Time-To-Live (TTL) for your cached content using the ttl parameter:

{
    {
        "role": "system",
        "content": ...,
        "cache_control": {
            "type": "ephemeral",
            "ttl": "3600s"  # 👈 Cache for 1 hour
        }
    },
    ...
}

TTL Format Requirements:

Must be a string ending with 's' for seconds
Must contain a positive number (can be decimal)
Examples: "3600s" (1 hour), "7200s" (2 hours), "1800s" (30 minutes), "1.5s" (1.5 seconds)
TTL Behavior:

If multiple cached messages have different TTLs, the first valid TTL encountered will be used
Invalid TTL formats are ignored and the cache will use Google's default expiration time
If no TTL is specified, Google's default cache expiration (approximately 1 hour) applies
Architecture Diagram

Notes:

Relevant code

Gemini Context Caching only allows 1 block of continuous messages to be cached.

If multiple non-continuous blocks contain cache_control - the first continuous block will be used. (sent to /cachedContent in the Gemini format)

The raw request to Gemini's /generateContent endpoint looks like this:

curl -X POST "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-001:generateContent?key=$GOOGLE_API_KEY" \
-H 'Content-Type: application/json' \
-d '{
      "contents": [
        {
          "parts":[{
            "text": "Please summarize this transcript"
          }],
          "role": "user"
        },
      ],
      "cachedContent": "'$CACHE_NAME'"
    }'



Example Usage
SDK
SDK with Custom TTL
PROXY
from litellm import completion 

for _ in range(2): 
    resp = completion(
        model="gemini/gemini-1.5-pro",
        messages=[
        # System Message
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "Here is the full text of a complex legal agreement" * 4000,
                        "cache_control": {"type": "ephemeral"}, # 👈 KEY CHANGE
                    }
                ],
            },
            # marked for caching with the cache_control parameter, so that this checkpoint can read from the previous cache.
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What are the key terms and conditions in this agreement?",
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }]
    )

    print(resp.usage) # 👈 2nd usage block will be less, since cached tokens used


Image Generation
SDK
PROXY
from litellm import completion 

response = completion(
    model="gemini/gemini-2.0-flash-exp-image-generation",
    messages=[{"role": "user", "content": "Generate an image of a cat"}],
    modalities=["image", "text"],
)
assert response.choices[0].message.content is not None # "data:image/png;base64,e4rr.."

Image Generation Pricing
Gemini image generation models (like gemini-3-pro-image-preview) return image_tokens in the response usage. These tokens are priced differently from text tokens:

Token Type	Price per 1M tokens	Price per token
Text output	$12	$0.000012
Image output	$120	$0.00012
The number of image tokens depends on the output resolution:

Resolution	Tokens per image	Cost per image
1K-2K (1024x1024 to 2048x2048)	1,120	$0.134
4K (4096x4096)	2,000	$0.24
LiteLLM automatically calculates costs using output_cost_per_image_token from the model pricing configuration.

Example response usage:

{
    "completion_tokens_details": {
        "reasoning_tokens": 225,
        "text_tokens": 0,
        "image_tokens": 1120
    }
}