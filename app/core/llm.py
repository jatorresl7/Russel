from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str = 'gpt-4o-mini'):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return response.choices[0].message.content


class GroqClient(LLMClient):
    def __init__(self, api_key: str, model: str = 'llama-3.3-70b-versatile'):
        from groq import Groq
        self.client = Groq(api_key=api_key)
        self.model = model

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return response.choices[0].message.content


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str = 'gemini-3.6-flash'):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )
        return response.text
