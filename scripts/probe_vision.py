import os, io, time
from typing import Optional
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

class Out(BaseModel):
    vendor: Optional[str]
    invoice_number: Optional[str]
    total: Optional[float]

font = ImageFont.load_default(size=30)
img = Image.new("RGB", (760, 260), "white")
d = ImageDraw.Draw(img)
d.text((30, 30), "ACME SUPPLIES PVT LTD", fill="black", font=font)
d.text((30, 90), "Invoice No: INV-2041", fill="black", font=font)
d.text((30, 150), "Total: Rs 3,776.00", fill="black", font=font)
buf = io.BytesIO(); img.save(buf, "PNG")

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
for name in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]:
    t = time.perf_counter()
    try:
        r = client.models.generate_content(
            model=name,
            contents=[types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"), "Extract vendor, invoice_number and total."],
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Out),
        )
        u = r.usage_metadata
        print(f"OK   {name:22s} {time.perf_counter()-t:4.1f}s in={u.prompt_token_count} out={u.candidates_token_count} thoughts={getattr(u, 'thoughts_token_count', None)}")
        print("     ", (r.text or "").replace("\n", " ")[:200])
    except Exception as e:
        print(f"FAIL {name:22s} {type(e).__name__}: {str(e).replace(chr(10), ' ')[:260]}")
    time.sleep(3)
