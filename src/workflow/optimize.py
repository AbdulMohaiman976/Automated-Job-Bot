import json
import time
from groq import Groq
from src.config import GROQ_API_KEY

def call_groq_with_retry(messages, model="llama-3.3-70b-versatile", temperature=0.1, max_retries=3):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not found in environment")
    
    client = Groq(api_key=GROQ_API_KEY)
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            print(f"Groq API error (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(2 ** attempt) # Exponential backoff

def tailor_cv(cv_data, job_description):
    prompt = f"""
    You are an expert resume optimizer. Your task is to rephrase and reorder the candidate's CV to better match the job description.
    
    STRICT CONSTRAINTS:
    1. DO NOT add any skills, experiences, or projects that are not present in the original CV.
    2. DO NOT lie or hallucinate.
    3. You can reword bullet points to highlight relevant technologies or keywords from the job description.
    4. You can reorder sections or bullet points to put the most relevant info first.
    5. Maintain the EXACT same JSON structure as the input.
    
    ORIGINAL CV DATA (JSON):
    {json.dumps(cv_data, indent=2)}
    
    JOB DESCRIPTION:
    {job_description}
    
    Return the optimized CV as a structured JSON with the same format as the input.
    Return ONLY the raw JSON starting with '{{' and ending with '}}'.
    """
    
    try:
        text = call_groq_with_retry([{"role": "user", "content": prompt}], temperature=0.1)
        
        # Extract JSON if model adds fluff
        if "{" in text and "}" in text:
            text = text[text.find("{"):text.rfind("}")+1]
            
        return json.loads(text)
    except Exception as e:
        print(f"Error tailoring CV: {e}")
        return cv_data  # Fallback to original

def generate_cover_letter(cv_data, job_description):
    prompt = f"""
    Write a professional and compelling cover letter for the candidate based on their CV and the job description.
    The cover letter should be personalized, addressing the specific requirements of the job.
    Keep it concise (under 300 words).
    Focus on how the candidate's existing experience solves the employer's problems.
    
    CV DATA:
    {json.dumps(cv_data, indent=2)}
    
    JOB DESCRIPTION:
    {job_description}
    
    Return ONLY the text of the cover letter. Do not include any headers like 'Subject:' or salutations like 'Dear Hiring Manager,' if you want them to be standard.
    """
    
    try:
        return call_groq_with_retry([{"role": "user", "content": prompt}], temperature=0.7)
    except Exception as e:
        print(f"Error generating cover letter: {e}")
        return "Professional cover letter could not be generated at this time."

