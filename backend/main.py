from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.health import router as health_router

app = FastAPI(
    title="Auditor Fiscal SAT Enterprise API",
    description="API for Document Intake, Parsing, SAT Validation and Conciliation.",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Welcome to Auditor Fiscal SAT API. Visit /docs for documentation."}
