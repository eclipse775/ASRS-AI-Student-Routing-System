# app/urgency.py
import google.generativeai as genai
import os

# Initialize Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

def detect_urgency(request_text: str) -> str:
    """
    Uses Gemini AI to analyze the context, meaning, and synonyms of the request
    to automatically classify its urgency level.
    Returns: 'HIGH', 'MEDIUM', or 'LOW'
    """
    if not request_text or not request_text.strip():
        return "LOW"

    prompt = f"""
    You are an AI routing assistant for a university support system.
    Analyze the following student request and determine its urgency level based on its semantic meaning and context.

    Urgency Criteria:
    - HIGH: Emergencies, medical/safety threats, system failures during exams, critical deadline errors.
    - MEDIUM: Important deadlines, tuition/payment issues, dormitory requests, grade appeals.
    - LOW: General inquiries, routine questions, library hours, general feedback.

    Student Request: "{request_text}"

    Instructions:
    - Return ONLY ONE WORD: HIGH, MEDIUM, or LOW.
    - Do not add punctuation or explanation.
    """

    try:
        response = model.generate_content(prompt)
        urgency = response.text.strip().upper()
        if urgency in ["HIGH", "MEDIUM", "LOW"]:
            return urgency
        return "LOW"
    except Exception as e:
        print(f"Error calling Gemini AI: {e}")
        return "LOW"