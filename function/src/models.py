from pydantic import BaseModel


class FileUploadModel(BaseModel):
    file_name: str
    content: str


class UserModel(BaseModel):
    username: str
    password: str


class UserFileModel(BaseModel):
    username: str
    file_name: str
