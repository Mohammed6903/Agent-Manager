from abc import ABC, abstractmethod
from sqlalchemy.orm import Session

class OAuth2FlowProvider(ABC):
    
    @abstractmethod
    def get_auth_url(self, agent_id: str, integration_name: str, db: Session = None) -> str:
        """
        Return the external authorization URL to redirect the user to.
        Called immediately when assign is hit for an OAuth integration.
        """
        ...

    @abstractmethod
    async def handle_callback(
        self,
        db: Session,
        agent_id: str,
        integration_name: str,
        code: str,
        **kwargs,
    ) -> dict:
        """
        Exchange authorization code for tokens and store them.
        Called by the generic callback route after user authorizes.
        Raise HTTPException on failure.
        Return a success dict on completion.
        """
        ...
