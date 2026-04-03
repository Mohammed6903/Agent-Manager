from typing import List

from agent_manager.integrations.google.base_google import BaseGoogleIntegration
from agent_manager.integrations.base import EndpointDef, MetadataFieldDef, MetadataFieldType


class YouTubeIntegration(BaseGoogleIntegration):
    """Integration definition for YouTube Data API."""

    name = "youtube"
    display_name = "YouTube"
    base_url = "https://www.googleapis.com/youtube/v3"

    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/channels?mine=true", description="Get the authenticated user's channel"),
        EndpointDef(method="GET", path="/channels?id={channel_id}", description="Get a channel by ID"),
        EndpointDef(method="GET", path="/search", description="Search for videos, channels, playlists"),
        EndpointDef(method="GET", path="/videos?id={video_id}", description="Get video details"),
        EndpointDef(method="GET", path="/playlists?mine=true", description="List user's playlists"),
        EndpointDef(method="GET", path="/playlistItems?playlistId={playlist_id}", description="List videos in a playlist"),
        EndpointDef(method="POST", path="/playlists", description="Create a playlist"),
        EndpointDef(method="POST", path="/playlistItems", description="Add a video to a playlist"),
        EndpointDef(method="GET", path="/subscriptions?mine=true", description="List user's subscriptions"),
        EndpointDef(method="GET", path="/commentThreads?videoId={video_id}", description="List comments on a video"),
    ]

    usage_instructions = (
        "YouTube Data API. Use GET /channels?mine=true for the user's channel. "
        "GET /search?q=... to search videos. GET /videos?id=... for details. "
        "GET /playlists?mine=true for playlists. Most endpoints need 'part' param (snippet, contentDetails, statistics)."
    )
