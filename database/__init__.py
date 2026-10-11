from .repository import DatabaseRepository

# Глобальный экземпляр репозитория
db_repo = DatabaseRepository()

__all__ = ['db_repo']