import os
import base64
from dotenv import load_dotenv
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from app.core.llm import OpenAIClient, GeminiClient, GroqClient

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'client_secret_107181798067-emk5ds0bt0igg3ppodncum0mupdvql8t.apps.googleusercontent.com.json'


def get_llm_client():
    if os.environ.get('GROQ_API_KEY'):
        return GroqClient(api_key=os.environ.get('GROQ_API_KEY'))
    if os.environ.get('GEMINI_API_KEY'):
        return GeminiClient(api_key=os.environ.get('GEMINI_API_KEY'))
    if os.environ.get('OPENAI_API_KEY'):
        return OpenAIClient(api_key=os.environ.get('OPENAI_API_KEY'))
    raise ValueError("No LLM API key found in environment")


def get_gmail_service():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('gmail', 'v1', credentials=creds)


def get_emails_today(service):
    today = datetime.now().strftime('%Y/%m/%d')
    result = service.users().messages().list(userId='me', q=f'after:{today}', maxResults=20).execute()
    messages = result.get('messages', [])
    emails = []
    for msg in messages:
        data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
        headers = {h['name']: h['value'] for h in data['payload']['headers']}
        emails.append({
            'subject': headers.get('Subject', '(sin asunto)'),
            'from': headers.get('From', '(desconocido)'),
            'body': extract_body(data['payload'])[:500]
        })
    return emails


def extract_body(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data', '')
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    body_data = payload.get('body', {}).get('data', '')
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
    return '(sin contenido)'


def summarize_emails(emails, llm):
    if not emails:
        print("No hay correos nuevos hoy.")
        return

    email_text = ""
    for i, e in enumerate(emails, 1):
        email_text += f"\n--- Correo {i} ---\nDe: {e['from']}\nAsunto: {e['subject']}\nCuerpo:\n{e['body']}\n"

    prompt = f"Resumí estos correos del día de forma clara y concisa en español. Destaca lo urgente o importante:\n{email_text}"
    result = llm.generate(prompt)

    print(f"\n=== Resumen Gmail - {datetime.now().strftime('%d/%m/%Y')} ===\n")
    print(result)


if __name__ == '__main__':
    service = get_gmail_service()
    emails = get_emails_today(service)
    print(f"Correos encontrados hoy: {len(emails)}")
    llm = get_llm_client()
    summarize_emails(emails, llm)
