import dropbox
from dropbox.exceptions import ApiError
import os
from dotenv import load_dotenv

load_dotenv()

class DropboxService:
    def __init__(self):
        access_token = os.getenv("DROPBOX_ACCESS_TOKEN")
        if not access_token:
            raise ValueError("DROPBOX_ACCESS_TOKEN не найден в .env файле")
        self.dbx = dropbox.Dropbox(access_token)
    
    def get_user_info(self):
        """Получить информацию о пользователе"""
        try:
            user = self.dbx.users_get_current_account()
            return {
                'name': user.name.display_name,
                'email': user.email,
                'country': user.country if hasattr(user, 'country') else None,
                'profile_photo_url': user.profile_photo_url if hasattr(user, 'profile_photo_url') else None
            }
        except Exception as e:
            return {'error': str(e)}
    
    def get_storage_info(self):
        """Получить информацию о хранилище"""
        try:
            usage = self.dbx.users_get_space_usage()
            used = usage.used
            allocation = usage.allocation
            
            # Проверяем тип выделенного пространства
            if hasattr(allocation, 'get_individual'):
                allocated = allocation.get_individual().allocated
            elif hasattr(allocation, 'allocated'):
                allocated = allocation.allocated
            elif hasattr(allocation, 'is_individual') and allocation.is_individual():
                allocated = allocation.get_individual().allocated
            else:
                allocated = 0
            
            free = allocated - used if allocated > 0 else 0
            
            return {
                'used': self._bytes_to_mb(used),
                'allocated': self._bytes_to_mb(allocated),
                'free': self._bytes_to_mb(free),
                'used_percentage': (used / allocated * 100) if allocated > 0 else 0
            }
        except Exception as e:
            return {'error': str(e)}
    
    def list_folder(self, path=""):
        """Просмотреть содержимое папки"""
        try:
            result = self.dbx.files_list_folder(path)
            items = []
            
            for entry in result.entries:
                item = {
                    'name': entry.name,
                    'path': entry.path_lower,
                    'is_folder': isinstance(entry, dropbox.files.FolderMetadata)
                }
                
                if isinstance(entry, dropbox.files.FileMetadata):
                    item.update({
                        'size': entry.size,
                        'modified': entry.server_modified,
                        'size_mb': self._bytes_to_mb(entry.size)
                    })
                
                items.append(item)
            
            return items
        except Exception as e:
            return {'error': str(e)}
    
    def create_folder(self, path):
        """Создать папку"""
        try:
            result = self.dbx.files_create_folder_v2(path)
            return {'success': True, 'folder': result.metadata.name}
        except Exception as e:
            return {'error': str(e)}
    
    def delete_item(self, path):
        """Удалить файл или папку"""
        try:
            self.dbx.files_delete_v2(path)
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}
    
    def upload_file(self, file_content, path):
        """Загрузить файл"""
        try:
            result = self.dbx.files_upload(file_content, path, mode=dropbox.files.WriteMode.overwrite)
            return {'success': True, 'file': result.name}
        except Exception as e:
            return {'error': str(e)}
    
    def download_file(self, path):
        """Скачать файл"""
        try:
            result = self.dbx.files_download(path)
            return {
                'success': True,
                'content': result[1].content,
                'filename': result[0].name
            }
        except Exception as e:
            return {'error': str(e)}
    
    def get_metadata(self, path):
        """Получить метаданные файла или папки"""
        try:
            metadata = self.dbx.files_get_metadata(path)
            
            result = {
                'name': metadata.name,
                'path': metadata.path_lower,
                'is_folder': isinstance(metadata, dropbox.files.FolderMetadata)
            }
            
            if isinstance(metadata, dropbox.files.FileMetadata):
                result.update({
                    'size': metadata.size,
                    'size_mb': self._bytes_to_mb(metadata.size),
                    'modified': metadata.server_modified,
                    'content_hash': metadata.content_hash if hasattr(metadata, 'content_hash') else None
                })
            
            return result
        except Exception as e:
            return {'error': str(e)}
    
    def create_shared_link(self, path):
        """Создать общую ссылку"""
        try:
            settings = dropbox.sharing.SharedLinkSettings(
                requested_visibility=dropbox.sharing.RequestedVisibility.public
            )
            result = self.dbx.sharing_create_shared_link_with_settings(path, settings)
            return {'success': True, 'url': result.url}
        except ApiError as e:
            if e.error.is_shared_link_already_exists():
                try:
                    links = self.dbx.sharing_list_shared_links(path=path)
                    if links.links:
                        return {'success': True, 'url': links.links[0].url}
                except:
                    pass
            return {'error': str(e)}
        except Exception as e:
            return {'error': str(e)}
    
    def list_shared_links(self):
        """Получить список общих ссылок"""
        try:
            result = self.dbx.sharing_list_shared_links()
            shared_items = []
            
            for link in result.links:
                shared_items.append({
                    'url': link.url,
                    'name': link.name,
                    'path': link.path_lower if hasattr(link, 'path_lower') else None
                })
            
            return shared_items
        except Exception as e:
            return {'error': str(e)}
    
    def search(self, query, path=""):
        """Поиск файлов"""
        try:
            search_options = dropbox.files.SearchOptions(
                path=path if path else None,
                filename_only=True,
                max_results=100
            )
            
            result = self.dbx.files_search_v2(query, options=search_options)
            matches = []
            
            for match in result.matches:
                if match.metadata:
                    metadata = match.metadata.get_metadata() if hasattr(match.metadata, 'get_metadata') else match.metadata
                    if metadata:
                        matches.append({
                            'name': metadata.name,
                            'path': metadata.path_lower,
                            'is_folder': isinstance(metadata, dropbox.files.FolderMetadata),
                            'match_type': match.match_type.value if hasattr(match.match_type, 'value') else str(match.match_type)
                        })
            
            return matches
        except Exception as e:
            return {'error': f'Ошибка поиска: {str(e)}'}
    
    def _bytes_to_mb(self, bytes_value):
        """Конвертировать байты в мегабайты"""
        if bytes_value is None:
            return 0
        return round(bytes_value / (1024 * 1024), 2)