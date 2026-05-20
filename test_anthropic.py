import os
import anthropic
from dotenv import load_dotenv

# Memuat file .env
load_dotenv()

key = os.getenv('ANTHROPIC_API_KEY', '')
print(f'API key prefix: {key[:15]}...{key[-4:] if len(key)>20 else ""}')
print(f'API key length: {len(key)} chars')

# Inisialisasi client
client = anthropic.Anthropic(api_key=key)

try:
    r = client.messages.create(
        model='claude-haiku-4-5',
        max_tokens=10,
        messages=[{'role': 'user', 'content': 'hi'}]
    )
    print('✅ SUCCESS! Credit working.')
    print('   Usage:', r.usage)
except anthropic.BadRequestError as e:
    print('❌ Bad request:', e.message)
    if 'credit' in str(e).lower():
        print('   → Likely cause: Spend limit = 0, OR credit not yet propagated')
        print('   → Fix: console.anthropic.com/settings/limits')
except anthropic.AuthenticationError as e:
    print('❌ Auth failed — API key invalid')
    print('   → Generate new key: console.anthropic.com/settings/keys')
except Exception as e:
    print(f'❌ {type(e).__name__}: {e}')