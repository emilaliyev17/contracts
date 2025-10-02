import google.generativeai as genai
genai.configure(api_key="AIzaSyAzBKPEzmXqGajRfSixHwO3yGY0wWnJuZM")

print("Available models:")
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(f"✓ {m.name}")
