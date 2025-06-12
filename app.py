import logging
import sys
import os
from datetime import datetime
from flask import Flask, jsonify, redirect, url_for
from flask_cors import CORS

# Добавляем текущую директорию в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def setup_logging():
    """Настройка системы логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('vpn_service.log'),
            logging.StreamHandler()
        ]
    )

    # Устанавливаем уровень логирования для библиотек
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def create_app():
    """Создание и настройка Flask приложения"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.urandom(24).hex()

    # Включаем CORS для API
    CORS(app)

    # Настройка для работы с flash сообщениями
    app.config['SESSION_TYPE'] = 'filesystem'

    try:
        # Импортируем и регистрируем админ-панель
        from admin_routes import admin_bp
        app.register_blueprint(admin_bp)
        logging.info("Админ-панель зарегистрирована")

        # Импортируем и регистрируем API маршруты
        from api.users import users_bp
        from api.servers import servers_bp
        from api.subscriptions import subscriptions_bp
        from api.payments import payments_bp

        app.register_blueprint(users_bp)
        app.register_blueprint(servers_bp)
        app.register_blueprint(subscriptions_bp)
        app.register_blueprint(payments_bp)
        logging.info("API маршруты зарегистрированы")

    except ImportError as e:
        logging.error(f"Ошибка импорта маршрутов: {e}")

    @app.route('/')
    def index():
        """Перенаправление на админ-панель"""
        return redirect(url_for('admin.index'))

    @app.route('/health')
    def health_check():
        """Проверка здоровья сервиса"""
        return jsonify({
            "service": "VPN Admin Panel",
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0"
        })

    @app.errorhandler(404)
    def not_found(error):
        """Обработчик 404 ошибки"""
        return jsonify({
            "success": False,
            "error": "Страница не найдена",
            "code": 404
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        """Обработчик 405 ошибки"""
        return jsonify({
            "success": False,
            "error": "Метод не разрешен",
            "code": 405
        }), 405

    @app.errorhandler(500)
    def internal_error(error):
        """Обработчик 500 ошибки"""
        logging.error(f"Внутренняя ошибка сервера: {error}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера",
            "code": 500
        }), 500

    return app


def init_database():
    """Инициализация базы данных"""
    try:
        from database.models import DatabaseInitializer
        DatabaseInitializer.init_database()
        logging.info("База данных инициализирована")
        return True
    except Exception as e:
        logging.error(f"Ошибка инициализации БД: {e}")
        return False


def start_monitoring():
    """Запуск мониторинга подписок"""
    try:
        from background.subscription_monitor import subscription_monitor
        subscription_monitor.start()
        logging.info("Мониторинг подписок запущен")
        return True
    except Exception as e:
        logging.error(f"Ошибка запуска мониторинга: {e}")
        return False


def main():
    """Главная функция запуска сервиса"""
    try:
        # Настройка логирования
        setup_logging()
        logger = logging.getLogger(__name__)

        logger.info("=" * 50)
        logger.info("Запуск VPN Admin Panel v2.0")
        logger.info("=" * 50)

        # Инициализация базы данных
        logger.info("Инициализация базы данных...")
        if not init_database():
            logger.error("Не удалось инициализировать базу данных")
            return

        # Создание приложения
        logger.info("Создание Flask приложения...")
        app = create_app()

        # Запуск мониторинга подписок
        logger.info("Запуск мониторинга подписок...")
        if not start_monitoring():
            logger.warning("Мониторинг подписок не запущен, но сервис продолжит работу")

        # Получаем конфигурацию
        try:
            from config import Config
            host = Config.API_HOST
            port = Config.API_PORT
            debug = Config.API_DEBUG
        except ImportError:
            logger.warning("Файл config.py не найден, используем значения по умолчанию")
            host = '0.0.0.0'
            port = 5000
            debug = True

        # Запуск веб-сервера
        logger.info(f"🚀 VPN Admin Panel запущен!")
        logger.info(f"🌐 Адрес: http://{host}:{port}")
        logger.info(f"🔧 Режим отладки: {'Включен' if debug else 'Отключен'}")
        logger.info("=" * 50)

        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True,
            use_reloader=False  # Отключаем автоперезагрузку чтобы избежать двойного запуска мониторинга
        )

    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания (Ctrl+C)")
        logger.info("Завершение работы VPN Admin Panel...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Остановка мониторинга
        try:
            from background.subscription_monitor import subscription_monitor
            subscription_monitor.stop()
            logger.info("Мониторинг подписок остановлен")
        except:
            pass

        logger.info("VPN Admin Panel остановлен")
        logger.info("=" * 50)


if __name__ == '__main__':
    main()
