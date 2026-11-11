import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Secure MLOps Prediction API", version="1.0.0")

class PredictionRequest(BaseModel):
    features: list[float] = Field(min_length=1, max_length=100)

@app.get("/")
def root():
    return {"service": "secure-mlops-api", "message": "API is running"}

@app.get("/health")
def health():
    # Never return secret values from health checks.
    return {
        "status": "healthy",
        "database_configured": bool(os.getenv("DB_USERNAME") and os.getenv("DB_PASSWORD")),
        "external_api_key_configured": bool(os.getenv("MODEL_API_KEY")),
    }

@app.post("/predict")
def predict(request: PredictionRequest):
    # A deterministic demo prediction. Replace this with a trained model later.
    score = sum(request.features) / len(request.features)
    label = "class-1" if score >= 0.5 else "class-0"
    return {"prediction": label, "score": round(score, 4)}
