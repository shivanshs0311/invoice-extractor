import os, time
from dotenv import load_dotenv
load_dotenv()
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
CANDIDATES = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite",
              "gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.8-flash"]
for name in CANDIDATES:
    t = time.perf_counter()
    try:
        r = client.models.generate_content(model=name, contents="Reply with the single word: ok")
        u = r.usage_metadata
        print(f"OK   {name:26s} {time.perf_counter()-t:4.1f}s in={u.prompt_token_count} out={u.candidates_token_count} thoughts={getattr(u, 'thoughts_token_count', None)} text={(r.text or '')!r}")
    except Exception as e:
        print(f"FAIL {name:26s} {type(e).__name__}: {str(e).replace(chr(10), ' ')[:220]}")
    time.sleep(2)
