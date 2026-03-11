from pydantic import BaseModel, Field

class CreateTweetRequest(BaseModel):
    agent_id: str = Field(..., description="The ID of the agent that has the Twitter integration assigned.")
    text: str = Field(..., description="The text content of the tweet to post.")

class SendDMRequest(BaseModel):
    agent_id: str = Field(..., description="The ID of the agent that has the Twitter integration assigned.")
    text: str = Field(..., description="The text content of the direct message to send.")
