from pydantic import BaseModel, Field

class CreateUgcPostRequest(BaseModel):
    agent_id: str = Field(..., description="The ID of the agent that has the LinkedIn integration assigned.")
    author_urn: str = Field(..., description="The URN of the author.")
    text: str = Field(..., description="The text content of the post.")

class InitializeImageUploadRequest(BaseModel):
    agent_id: str = Field(..., description="The ID of the agent that has the LinkedIn integration assigned.")
    person_urn: str = Field(..., description="The URN of the person initializing the upload.")
