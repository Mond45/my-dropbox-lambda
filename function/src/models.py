from pydantic import BaseModel

class FileUploadBody(BaseModel):
    key: str
    content: str
