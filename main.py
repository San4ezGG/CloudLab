import os
from typing import Optional
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import tempfile
from dotenv import load_dotenv

from utils import DropboxService

# Загружаем переменные окружения
load_dotenv()

app = FastAPI(title="Dropbox Web Manager")

# Настройка шаблонов и статических файлов
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Инициализация Dropbox сервиса
DROPBOX_ACCESS_TOKEN = os.getenv("DROPBOX_ACCESS_TOKEN")
if not DROPBOX_ACCESS_TOKEN:
    print("⚠️ ВНИМАНИЕ: DROPBOX_ACCESS_TOKEN не найден в .env файле")
    dbx_service = None
else:
    try:
        dbx_service = DropboxService()
        print("✅ Dropbox сервис инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации Dropbox: {e}")
        dbx_service = None

# Главная страница - Dashboard
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not dbx_service:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Dropbox сервис не инициализирован. Проверьте токен доступа в .env файле."
        })
    
    try:
        user_info = dbx_service.get_user_info()
        storage_info = dbx_service.get_storage_info()
        
        # Для отладки
        print("User Info:", user_info)
        print("Storage Info:", storage_info)
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "user_info": user_info,
            "storage_info": storage_info
        })
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Ошибка при загрузке данных: {str(e)}"
        })

# Просмотр содержимого папки
@app.get("/folder", response_class=HTMLResponse)
async def list_folder(request: Request, path: str = ""):
    if not dbx_service:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Dropbox сервис не инициализирован"
        })
    
    try:
        # Получаем информацию о текущей папке
        if path:
            current_folder = dbx_service.get_metadata(path)
            if 'error' in current_folder:
                current_folder = {'name': 'Корневая папка', 'path': ''}
        else:
            current_folder = {'name': 'Корневая папка', 'path': ''}
        
        # Получаем содержимое папки
        items = dbx_service.list_folder(path)
        
        # Определяем родительскую папку
        parent_path = ""
        if path:
            path_parts = path.rstrip('/').split('/')
            if len(path_parts) > 1:
                parent_path = '/'.join(path_parts[:-1])
        
        return templates.TemplateResponse("folder.html", {
            "request": request,
            "items": items if not isinstance(items, dict) else [],
            "current_folder": current_folder,
            "current_path": path,
            "parent_path": parent_path,
            "error": items.get('error') if isinstance(items, dict) else None
        })
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e)
        })

# Создание новой папки
@app.post("/create-folder")
async def create_folder(
    request: Request,
    path: str = Form(""),
    folder_name: str = Form(...)
):
    if not dbx_service:
        raise HTTPException(status_code=500, detail="Dropbox сервис не инициализирован")
    
    try:
        folder_path = f"{path}/{folder_name}" if path else f"/{folder_name}"
        result = dbx_service.create_folder(folder_path)
        
        if 'error' in result:
            return RedirectResponse(f"/folder?path={path}&error={result['error']}", status_code=302)
        
        return RedirectResponse(f"/folder?path={path}&success=Папка '{folder_name}' создана", status_code=302)
    except Exception as e:
        return RedirectResponse(f"/folder?path={path}&error={str(e)}", status_code=302)

# Удаление файла или папки
@app.post("/delete")
async def delete_item(
    request: Request,
    item_path: str = Form(...),
    current_path: str = Form("")
):
    if not dbx_service:
        raise HTTPException(status_code=500, detail="Dropbox сервис не инициализирован")
    
    try:
        result = dbx_service.delete_item(item_path)
        
        if 'error' in result:
            return RedirectResponse(f"/folder?path={current_path}&error={result['error']}", status_code=302)
        
        return RedirectResponse(f"/folder?path={current_path}&success=Элемент удален", status_code=302)
    except Exception as e:
        return RedirectResponse(f"/folder?path={current_path}&error={str(e)}", status_code=302)

# Страница загрузки файла
@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, path: str = ""):
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "current_path": path
    })

# Загрузка файла
@app.post("/upload")
async def upload_file(
    request: Request,
    path: str = Form(""),
    file: UploadFile = File(...)
):
    if not dbx_service:
        raise HTTPException(status_code=500, detail="Dropbox сервис не инициализирован")
    
    try:
        file_content = await file.read()
        file_path = f"{path}/{file.filename}" if path else f"/{file.filename}"
        
        result = dbx_service.upload_file(file_content, file_path)
        
        if 'error' in result:
            return RedirectResponse(f"/folder?path={path}&error={result['error']}", status_code=302)
        
        return RedirectResponse(f"/folder?path={path}&success=Файл '{file.filename}' загружен", status_code=302)
    except Exception as e:
        return RedirectResponse(f"/folder?path={path}&error={str(e)}", status_code=302)
    finally:
        await file.close()

# Скачивание файла
@app.get("/download")
async def download_file(file_path: str):
    if not dbx_service:
        raise HTTPException(status_code=500, detail="Dropbox сервис не инициализирован")
    
    try:
        result = dbx_service.download_file(file_path)
        
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])
        
        # Создаем временный файл для скачивания
        with tempfile.NamedTemporaryFile(delete=False, suffix=result['filename']) as tmp_file:
            tmp_file.write(result['content'])
            tmp_file.flush()
            
            return FileResponse(
                tmp_file.name,
                filename=result['filename'],
                media_type='application/octet-stream'
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Создание общей ссылки
@app.post("/share")
async def create_shared_link(
    request: Request,
    item_path: str = Form(...),
    current_path: str = Form("")
):
    if not dbx_service:
        raise HTTPException(status_code=500, detail="Dropbox сервис не инициализирован")
    
    try:
        result = dbx_service.create_shared_link(item_path)
        
        if 'error' in result:
            return RedirectResponse(f"/folder?path={current_path}&error={result['error']}", status_code=302)
        
        return RedirectResponse(f"/folder?path={current_path}&success=Ссылка создана: {result['url']}", status_code=302)
    except Exception as e:
        return RedirectResponse(f"/folder?path={current_path}&error={str(e)}", status_code=302)

# Просмотр общих ссылок
@app.get("/shared-links", response_class=HTMLResponse)
async def shared_links(request: Request):
    if not dbx_service:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Dropbox сервис не инициализирован"
        })
    
    try:
        links = dbx_service.list_shared_links()
        
        return templates.TemplateResponse("shared_links.html", {
            "request": request,
            "links": links if not isinstance(links, dict) else [],
            "error": links.get('error') if isinstance(links, dict) else None
        })
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e)
        })

# Поиск файлов
@app.get("/search", response_class=HTMLResponse)
async def search_files(
    request: Request,
    q: str = "",
    path: str = ""
):
    if not dbx_service:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Dropbox сервис не инициализирован"
        })
    
    try:
        if q:
            results = dbx_service.search(q, path)
        else:
            results = []
        
        return templates.TemplateResponse("search.html", {
            "request": request,
            "query": q,
            "search_path": path,
            "results": results if not isinstance(results, dict) else [],
            "error": results.get('error') if isinstance(results, dict) else None
        })
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e)
        })

# Получение метаданных файла (JSON API)
@app.get("/metadata")
async def get_metadata(file_path: str):
    if not dbx_service:
        raise HTTPException(status_code=500, detail="Dropbox сервис не инициализирован")
    
    try:
        metadata = dbx_service.get_metadata(file_path)
        
        if 'error' in metadata:
            return JSONResponse({"error": metadata['error']}, status_code=400)
        
        return JSONResponse({"success": True, "metadata": metadata})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

# Статус приложения
@app.get("/status")
async def status():
    return {
        "status": "ok",
        "dropbox_initialized": dbx_service is not None,
        "token_exists": bool(DROPBOX_ACCESS_TOKEN)
    }

# API эндпоинты
@app.get("/api/user")
async def api_get_user():
    if not dbx_service:
        raise HTTPException(status_code=500, detail="Dropbox сервис не инициализирован")
    
    return dbx_service.get_user_info()

@app.get("/api/storage")
async def api_get_storage():
    if not dbx_service:
        raise HTTPException(status_code=500, detail="Dropbox сервис не инициализирован")
    
    return dbx_service.get_storage_info()

@app.get("/api/folder")
async def api_list_folder(path: str = ""):
    if not dbx_service:
        raise HTTPException(status_code=500, detail="Dropbox сервис не инициализирован")
    
    return dbx_service.list_folder(path)

# Или, если хотите оставить возможность запуска из main.py, сделайте так:
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)