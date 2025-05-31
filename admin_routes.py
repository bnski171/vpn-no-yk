from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta
from services.user_service import UserService
from services.server_service import ServerService
from services.subscription_service import SubscriptionService
from database.connection import db_manager
from utils.helpers import seconds_to_human_readable
import math
import random
import string
import logging

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ============================================================================
# ГЛАВНАЯ СТРАНИЦА
# ============================================================================

@admin_bp.route('/')
def index():
    """Главная страница админ-панели"""
    try:
        # Получаем статистику
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Общая статистика
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end > ?", (datetime.now(),))
            active_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM servers")
            total_servers = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM servers WHERE is_active = TRUE")
            active_servers = cursor.fetchone()[0]

            # Последняя активность
            cursor.execute("""
                SELECT action, details, timestamp FROM user_activity_log 
                ORDER BY timestamp DESC LIMIT 10
            """)
            recent_activity = [dict(row) for row in cursor.fetchall()]

            # Статистика по серверам
            cursor.execute("""
                SELECT s.name, s.domain, COUNT(u.id) as user_count,
                       s.id, s.api_url, s.api_token, s.is_active
                FROM servers s
                LEFT JOIN users u ON s.id = u.server_id
                GROUP BY s.id
                ORDER BY s.name
            """)
            servers_data = cursor.fetchall()

        # Получаем статус каждого сервера
        server_stats = []
        for server_row in servers_data:
            server = dict(server_row)

            if server['is_active']:
                status = ServerService.get_server_status(server)
                is_online = not status.get('error')
                cpu_usage = 'N/A'
                memory_usage = 'N/A'

                if status.get('system'):
                    cpu_usage = status['system'].get('cpu', {}).get('percent', 'N/A')
                    memory_usage = status['system'].get('memory', {}).get('percent', 'N/A')
            else:
                is_online = False
                cpu_usage = 'N/A'
                memory_usage = 'N/A'

            server_stats.append({
                'name': server['name'],
                'domain': server['domain'],
                'user_count': server['user_count'],
                'is_online': is_online,
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage
            })

        stats = {
            'total_users': total_users,
            'active_users': active_users,
            'total_servers': total_servers,
            'active_servers': active_servers
        }

        # Уведомления (проверяем проблемы)
        notifications = []

        # Проверяем истекающие подписки
        tomorrow = datetime.now() + timedelta(hours=24)
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM users 
                WHERE subscription_end BETWEEN ? AND ? AND subscription_end > ?
            """, (datetime.now(), tomorrow, datetime.now()))
            expiring_count = cursor.fetchone()[0]

            if expiring_count > 0:
                notifications.append({
                    'type': 'warning',
                    'message': f'⚠️ У {expiring_count} пользователей истекает подписка в ближайшие 24 часа'
                })

        # Проверяем оффлайн серверы
        offline_servers = [s for s in server_stats if not s['is_online']]
        if offline_servers:
            notifications.append({
                'type': 'danger',
                'message': f'❌ {len(offline_servers)} серверов недоступны'
            })

        return render_template('index.html',
                               stats=stats,
                               recent_activity=recent_activity,
                               server_stats=server_stats,
                               notifications=notifications)

    except Exception as e:
        logger.error(f"Ошибка загрузки главной страницы: {e}")
        flash(f'Ошибка загрузки данных: {str(e)}', 'error')
        return render_template('index.html',
                               stats={'total_users': 0, 'active_users': 0, 'total_servers': 0, 'active_servers': 0},
                               recent_activity=[],
                               server_stats=[],
                               notifications=[])


# ============================================================================
# ПОЛЬЗОВАТЕЛИ
# ============================================================================

@admin_bp.route('/users')
def users_list():
    """Список пользователей с пагинацией и фильтрами"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    server_filter = request.args.get('server', '')

    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Строим запрос с фильтрами
            where_conditions = []
            params = []

            if search:
                where_conditions.append("(u.telegram_id LIKE ? OR u.email LIKE ?)")
                params.extend([f'%{search}%', f'%{search}%'])

            if status_filter == 'active':
                where_conditions.append("u.subscription_end > ?")
                params.append(datetime.now())
            elif status_filter == 'expired':
                where_conditions.append("u.subscription_end <= ?")
                params.append(datetime.now())

            if server_filter:
                where_conditions.append("u.server_id = ?")
                params.append(server_filter)

            where_clause = " AND ".join(where_conditions)
            if where_clause:
                where_clause = "WHERE " + where_clause

            # Подсчет общего количества
            count_query = f"""
                SELECT COUNT(*) FROM users u
                LEFT JOIN servers s ON u.server_id = s.id
                {where_clause}
            """
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]

            # Получение пользователей для текущей страницы
            offset = (page - 1) * per_page
            users_query = f"""
                SELECT u.*, s.name as server_name, s.domain as server_domain
                FROM users u
                LEFT JOIN servers s ON u.server_id = s.id
                {where_clause}
                ORDER BY u.created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(users_query, params + [per_page, offset])
            users = cursor.fetchall()

            # Добавляем расчет времени до истечения
            now = datetime.now()
            users_with_time = []
            for user in users:
                user_dict = dict(user)
                user_dict['is_subscription_active'] = user_dict['subscription_end'] > now
                user_dict['time_left_seconds'] = max(0, int((user_dict['subscription_end'] - now).total_seconds()))
                users_with_time.append(user_dict)

            # Статистика для отображения
            cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end > ?", (now,))
            active_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end <= ?", (now,))
            expired_count = cursor.fetchone()[0]

            # Истекают в ближайшие 24 часа
            tomorrow = now + timedelta(hours=24)
            cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end BETWEEN ? AND ?", (now, tomorrow))
            expiring_soon = cursor.fetchone()[0]

            # Получаем серверы для фильтра
            cursor.execute("SELECT id, name FROM servers WHERE is_active = TRUE ORDER BY name")
            servers = cursor.fetchall()

        # Пагинация
        pages = math.ceil(total / per_page)
        pagination = {
            'page': page,
            'pages': pages,
            'per_page': per_page,
            'total': total,
            'has_prev': page > 1,
            'has_next': page < pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < pages else None,
            'iter_pages': lambda: range(max(1, page - 2), min(pages + 1, page + 3))
        }

        users_stats = {
            'active_count': active_count,
            'expired_count': expired_count,
            'expiring_soon': expiring_soon
        }

        return render_template('users/list.html',
                               users=users_with_time,
                               pagination=pagination,
                               users_stats=users_stats,
                               servers=servers)

    except Exception as e:
        logger.error(f"Ошибка загрузки пользователей: {e}")
        flash(f'Ошибка загрузки пользователей: {str(e)}', 'error')
        return render_template('users/list.html', users=[], pagination={}, users_stats={}, servers=[])


@admin_bp.route('/users/<int:user_id>')
def user_details(user_id):
    """Детальная информация о пользователе"""
    try:
        user = UserService.get_user_by_id(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.users_list'))

        # Получаем VPN конфигурацию
        vpn_config = None
        if user['is_subscription_active']:
            success, message, config = UserService.get_user_vpn_config(user['telegram_id'])
            if success:
                vpn_config = config

        # Добавляем время до истечения в секундах
        now = datetime.now()
        user['time_left_seconds'] = max(0, int((user['subscription_end'] - now).total_seconds()))

        # Получаем историю активности
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT action, details, timestamp FROM user_activity_log 
                WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20
            """, (user_id,))
            user_activity = [dict(row) for row in cursor.fetchall()]

        return render_template('users/details.html',
                               user=user,
                               vpn_config=vpn_config,
                               user_activity=user_activity)

    except Exception as e:
        logger.error(f"Ошибка загрузки пользователя {user_id}: {e}")
        flash(f'Ошибка загрузки пользователя: {str(e)}', 'error')
        return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/add', methods=['GET', 'POST'])
def add_user():
    """Добавление нового пользователя"""
    if request.method == 'POST':
        telegram_id = request.form.get('telegram_id', '').strip()
        subscription_seconds = int(request.form.get('subscription_seconds', 0))

        if not telegram_id:
            flash('Telegram ID обязателен', 'error')
            return redirect(url_for('admin.add_user'))

        # Валидация Telegram ID
        if not telegram_id.isdigit() or len(telegram_id) < 5 or len(telegram_id) > 15:
            flash('Telegram ID должен содержать только цифры и быть длиной от 5 до 15 символов', 'error')
            return redirect(url_for('admin.add_user'))

        success, message, user_data = UserService.create_user(telegram_id, subscription_seconds)

        if success:
            flash(f'Пользователь успешно создан: {message}', 'success')
            return redirect(url_for('admin.user_details', user_id=user_data['id']))
        else:
            flash(f'Ошибка создания пользователя: {message}', 'error')

    # Получаем серверы для выбора
    servers = ServerService.get_active_servers()
    for server in servers:
        # Подсчитываем пользователей на каждом сервере
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE server_id = ?", (server['id'],))
            server['user_count'] = cursor.fetchone()[0]

    return render_template('users/add.html', servers=servers)


@admin_bp.route('/users/<int:user_id>/extend')
def extend_user_page(user_id):
    """Страница продления подписки пользователя"""
    try:
        user = UserService.get_user_by_id(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.users_list'))

        # Добавляем время до истечения в секундах
        now = datetime.now()
        user['time_left_seconds'] = max(0, int((user['subscription_end'] - now).total_seconds()))

        # Получаем доступные промокоды
        available_promocodes = SubscriptionService.get_active_promocodes()
        for promo in available_promocodes:
            promo['duration_human'] = seconds_to_human_readable(promo['duration_seconds'])

        return render_template('users/extend_subscription.html',
                               user=user,
                               available_promocodes=available_promocodes)

    except Exception as e:
        logger.error(f"Ошибка загрузки страницы продления для пользователя {user_id}: {e}")
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/extend-seconds', methods=['POST'])
def extend_user_subscription_seconds(user_id):
    """Продление подписки пользователя на указанное количество секунд"""
    try:
        seconds = int(request.form.get('seconds', 0))

        if seconds <= 0:
            flash('Количество секунд должно быть больше 0', 'error')
            return redirect(url_for('admin.user_details', user_id=user_id))

        user = UserService.get_user_by_id(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.users_list'))

        success, message = UserService.update_subscription(user['telegram_id'], seconds)

        if success:
            # Форматируем время для отображения
            time_str = seconds_to_human_readable(seconds)
            flash(f'Подписка продлена на {time_str} ({seconds:,} сек)', 'success')
        else:
            flash(f'Ошибка продления подписки: {message}', 'error')

    except ValueError:
        flash('Некорректное количество секунд', 'error')
    except Exception as e:
        logger.error(f"Ошибка продления подписки пользователя {user_id}: {e}")
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('admin.user_details', user_id=user_id))


@admin_bp.route('/users/<int:user_id>/set-end-date', methods=['POST'])
def set_user_subscription_end_date(user_id):
    """Установка точной даты окончания подписки"""
    try:
        end_date_str = request.form.get('end_date')

        if not end_date_str:
            flash('Дата окончания не указана', 'error')
            return redirect(url_for('admin.user_details', user_id=user_id))

        # Парсим дату
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Неверный формат даты', 'error')
            return redirect(url_for('admin.user_details', user_id=user_id))

        # Проверяем, что дата в будущем
        if end_date <= datetime.now():
            flash('Дата окончания должна быть в будущем', 'error')
            return redirect(url_for('admin.user_details', user_id=user_id))

        user = UserService.get_user_by_id(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.users_list'))

        # Обновляем дату окончания подписки напрямую в БД
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET subscription_end = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (end_date, user_id))

            # Логируем изменение
            cursor.execute("""
                INSERT INTO user_activity_log (user_id, action, details)
                VALUES (?, ?, ?)
            """, (user_id, "SUBSCRIPTION_SET_DATE", f"Set end date to: {end_date}"))

            conn.commit()

        flash(f'Дата окончания подписки установлена: {end_date.strftime("%d.%m.%Y %H:%M")}', 'success')

    except Exception as e:
        logger.error(f"Ошибка установки даты окончания подписки пользователя {user_id}: {e}")
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('admin.user_details', user_id=user_id))


@admin_bp.route('/users/<int:user_id>/activate-promocode', methods=['POST'])
def activate_user_promocode(user_id):
    """Активация промокода для пользователя"""
    try:
        promocode = request.form.get('promocode', '').strip().upper()

        if not promocode:
            flash('Промокод не указан', 'error')
            return redirect(url_for('admin.user_details', user_id=user_id))

        user = UserService.get_user_by_id(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.users_list'))

        success, message = SubscriptionService.activate_promocode(user['telegram_id'], promocode)

        if success:
            flash(f'Промокод активирован: {message}', 'success')
        else:
            flash(f'Ошибка активации промокода: {message}', 'error')

    except Exception as e:
        logger.error(f"Ошибка активации промокода для пользователя {user_id}: {e}")
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('admin.user_details', user_id=user_id))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    """Удаление пользователя"""
    try:
        success, message = UserService.delete_user(user_id)

        if success:
            flash(f'Пользователь удален: {message}', 'success')
            return redirect(url_for('admin.users_list'))
        else:
            flash(f'Ошибка удаления: {message}', 'error')

    except Exception as e:
        logger.error(f"Ошибка удаления пользователя {user_id}: {e}")
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('admin.user_details', user_id=user_id))


@admin_bp.route('/users/<int:user_id>/reset-subscription', methods=['POST'])
def reset_user_subscription(user_id):
    """Обнуление подписки пользователя"""
    try:
        user = UserService.get_user_by_id(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.users_list'))

        # Устанавливаем дату окончания подписки на текущий момент
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET subscription_end = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (datetime.now(), user_id))

            # Логируем действие
            cursor.execute("""
                INSERT INTO user_activity_log (user_id, action, details)
                VALUES (?, ?, ?)
            """, (user_id, "SUBSCRIPTION_RESET", "Subscription reset by admin"))

            conn.commit()

        flash('Подписка пользователя обнулена', 'success')

    except Exception as e:
        logger.error(f"Ошибка обнуления подписки пользователя {user_id}: {e}")
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('admin.user_details', user_id=user_id))


# ============================================================================
# СЕРВЕРЫ
# ============================================================================

@admin_bp.route('/servers')
def servers_list():
    """Список серверов"""
    try:
        servers = ServerService.get_all_servers()

        # Получаем статус и статистику для каждого сервера
        for server in servers:
            # Получаем статус сервера
            if server['is_active']:
                status = ServerService.get_server_status(server)
                server['status'] = status
            else:
                server['status'] = {'error': 'Сервер отключен'}

            # Подсчитываем пользователей
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users WHERE server_id = ?", (server['id'],))
                server['user_count'] = cursor.fetchone()[0]

        # Статистика серверов
        online_count = sum(1 for s in servers if s['is_active'] and not s['status'].get('error'))
        total_users = sum(s['user_count'] for s in servers)
        avg_load = 0

        if servers:
            load_values = []
            for s in servers:
                if s['status'].get('system', {}).get('cpu', {}).get('percent'):
                    try:
                        load_values.append(float(s['status']['system']['cpu']['percent']))
                    except (ValueError, TypeError):
                        pass

            if load_values:
                avg_load = round(sum(load_values) / len(load_values), 1)

        servers_stats = {
            'online_count': online_count,
            'total_users': total_users,
            'avg_load': avg_load
        }

        return render_template('servers/list.html',
                               servers=servers,
                               servers_stats=servers_stats)

    except Exception as e:
        logger.error(f"Ошибка загрузки серверов: {e}")
        flash(f'Ошибка загрузки серверов: {str(e)}', 'error')
        return render_template('servers/list.html', servers=[], servers_stats={})


@admin_bp.route('/servers/add', methods=['GET', 'POST'])
def add_server():
    """Добавление нового сервера"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        domain = request.form.get('domain', '').strip()
        api_url = request.form.get('api_url', '').strip()
        api_token = request.form.get('api_token', '').strip()

        # Валидация
        if not all([name, domain, api_url, api_token]):
            flash('Все поля обязательны для заполнения', 'error')
            return render_template('servers/add.html')

        success, message = ServerService.create_server(name, domain, api_url, api_token)

        if success:
            flash(f'Сервер успешно добавлен: {message}', 'success')
            return redirect(url_for('admin.servers_list'))
        else:
            flash(f'Ошибка добавления сервера: {message}', 'error')

    return render_template('servers/add.html')


@admin_bp.route('/servers/<int:server_id>')
def server_details(server_id):
    """Детальная информация о сервере"""
    try:
        server = ServerService.get_server_by_id(server_id)
        if not server:
            flash('Сервер не найден', 'error')
            return redirect(url_for('admin.servers_list'))

        # Получаем статус сервера
        status = ServerService.get_server_status(server)

        # Получаем пользователей на сервере
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.*, (u.subscription_end > ?) as is_subscription_active
                FROM users u
                WHERE u.server_id = ?
                ORDER BY u.subscription_end DESC
                LIMIT 50
            """, (datetime.now(), server_id))
            server_users = [dict(row) for row in cursor.fetchall()]

            # Подсчитываем общее количество пользователей
            cursor.execute("SELECT COUNT(*) FROM users WHERE server_id = ?", (server_id,))
            server['user_count'] = cursor.fetchone()[0]

        # Время ответа (можно добавить измерение)
        response_time = None
        current_time = datetime.now()

        return render_template('servers/status.html',
                               server=server,
                               status=status,
                               server_users=server_users,
                               response_time=response_time,
                               current_time=current_time)

    except Exception as e:
        logger.error(f"Ошибка загрузки сервера {server_id}: {e}")
        flash(f'Ошибка загрузки сервера: {str(e)}', 'error')
        return redirect(url_for('admin.servers_list'))


@admin_bp.route('/servers/<int:server_id>/edit', methods=['GET', 'POST'])
def edit_server(server_id):
    """Редактирование сервера"""
    try:
        server = ServerService.get_server_by_id(server_id)
        if not server:
            flash('Сервер не найден', 'error')
            return redirect(url_for('admin.servers_list'))

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            domain = request.form.get('domain', '').strip()
            api_url = request.form.get('api_url', '').strip()
            api_token = request.form.get('api_token', '').strip()

            # Валидация
            if not all([name, domain, api_url, api_token]):
                flash('Все поля обязательны для заполнения', 'error')
                return render_template('servers/edit.html', server=server)

            success, message = ServerService.update_server(server_id, name, domain, api_url, api_token)

            if success:
                flash(f'Сервер успешно обновлен: {message}', 'success')
                return redirect(url_for('admin.server_details', server_id=server_id))
            else:
                flash(f'Ошибка обновления сервера: {message}', 'error')

        return render_template('servers/edit.html', server=server)

    except Exception as e:
        logger.error(f"Ошибка редактирования сервера {server_id}: {e}")
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('admin.servers_list'))


@admin_bp.route('/servers/<int:server_id>/toggle', methods=['POST'])
def toggle_server_status(server_id):
    """Переключение статуса сервера"""
    try:
        success, message = ServerService.toggle_server_status(server_id)

        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "error": message}), 400

    except Exception as e:
        logger.error(f"Ошибка переключения статуса сервера {server_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/servers/<int:server_id>/delete', methods=['POST'])
def delete_server(server_id):
    """Удаление сервера"""
    try:
        success, message = ServerService.delete_server(server_id)

        if success:
            flash(f'Сервер удален: {message}', 'success')
            return redirect(url_for('admin.servers_list'))
        else:
            flash(f'Ошибка удаления: {message}', 'error')

    except Exception as e:
        logger.error(f"Ошибка удаления сервера {server_id}: {e}")
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('admin.servers_list'))


@admin_bp.route('/servers/test-connection', methods=['POST'])
def test_server_connection():
    """Тестирование соединения с сервером"""
    try:
        name = request.form.get('name', '').strip()
        domain = request.form.get('domain', '').strip()
        api_url = request.form.get('api_url', '').strip()
        api_token = request.form.get('api_token', '').strip()

        if not all([name, domain, api_url, api_token]):
            return jsonify({
                "success": False,
                "error": "Все поля обязательны для заполнения"
            }), 400

        # Создаем временный объект сервера для тестирования
        test_server = {
            'name': name,
            'domain': domain,
            'api_url': api_url,
            'api_token': api_token
        }

        # Тестируем соединение
        import time
        start_time = time.time()
        status = ServerService.get_server_status(test_server)
        response_time = round((time.time() - start_time) * 1000, 2)

        if status.get('error'):
            return jsonify({
                "success": False,
                "error": status['error'],
                "details": f"Время ответа: {response_time}мс"
            })

        # Извлекаем полезную информацию из статуса
        server_info = {
            "status": "Online",
            "response_time": f"{response_time}мс"
        }

        if status.get('xray', {}).get('version'):
            server_info['xray_version'] = status['xray']['version']

        if status.get('system', {}).get('uptime'):
            server_info['uptime'] = status['system']['uptime']

        return jsonify({
            "success": True,
            "server_info": server_info,
            "response_time": f"{response_time}мс"
        })

    except Exception as e:
        logger.error(f"Ошибка тестирования соединения: {e}")
        return jsonify({
            "success": False,
            "error": f"Ошибка тестирования: {str(e)}"
        }), 500


@admin_bp.route('/servers/refresh-statuses', methods=['POST'])
def refresh_servers_statuses():
    """Обновление статусов всех серверов"""
    try:
        return jsonify({"success": True, "message": "Статусы обновлены"})
    except Exception as e:
        logger.error(f"Ошибка обновления статусов серверов: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# ПРОМОКОДЫ
# ============================================================================

@admin_bp.route('/promocodes')
def promocodes_list():
    """Список промокодов"""
    try:
        search = request.args.get('search', '')
        status_filter = request.args.get('status', '')
        duration_filter = request.args.get('duration', '')

        # Получаем все промокоды
        promocodes = SubscriptionService.get_all_promocodes()

        # Применяем фильтры
        if search:
            promocodes = [p for p in promocodes if search.upper() in p['code'].upper()]

        if status_filter == 'active':
            promocodes = [p for p in promocodes if p['is_active'] and p['current_activations'] < p['max_activations']]
        elif status_filter == 'inactive':
            promocodes = [p for p in promocodes if not p['is_active']]
        elif status_filter == 'exhausted':
            promocodes = [p for p in promocodes if p['current_activations'] >= p['max_activations']]

        if duration_filter:
            try:
                duration_seconds = int(duration_filter)
                promocodes = [p for p in promocodes if p['duration_seconds'] == duration_seconds]
            except ValueError:
                pass

        # Добавляем человекочитаемую продолжительность
        for promo in promocodes:
            promo['duration_human'] = seconds_to_human_readable(promo['duration_seconds'])

        # Статистика промокодов
        active_count = sum(1 for p in promocodes if p['is_active'] and p['current_activations'] < p['max_activations'])
        total_activations = sum(p['current_activations'] for p in promocodes)
        available_activations = sum(max(0, p['max_activations'] - p['current_activations']) for p in promocodes)

        promocodes_stats = {
            'active_count': active_count,
            'total_activations': total_activations,
            'available_activations': available_activations
        }

        return render_template('promocodes/list.html',
                               promocodes=promocodes,
                               promocodes_stats=promocodes_stats)

    except Exception as e:
        logger.error(f"Ошибка загрузки промокодов: {e}")
        flash(f'Ошибка загрузки промокодов: {str(e)}', 'error')
        return render_template('promocodes/list.html', promocodes=[], promocodes_stats={})


@admin_bp.route('/promocodes/add', methods=['GET', 'POST'])
def add_promocode():
    """Добавление нового промокода"""
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        duration_seconds = int(request.form.get('duration_seconds', 0))
        max_activations = int(request.form.get('max_activations', 0))

        if not code:
            flash('Код промокода обязателен', 'error')
            return render_template('promocodes/add.html')

        if duration_seconds <= 0:
            flash('Продолжительность должна быть больше 0', 'error')
            return render_template('promocodes/add.html')

        if max_activations <= 0:
            flash('Количество активаций должно быть больше 0', 'error')
            return render_template('promocodes/add.html')

        success, message = SubscriptionService.create_promocode(code, duration_seconds, max_activations)

        if success:
            flash(f'Промокод успешно создан: {message}', 'success')
            return redirect(url_for('admin.promocodes_list'))
        else:
            flash(f'Ошибка создания промокода: {message}', 'error')

    return render_template('promocodes/add.html')


@admin_bp.route('/promocodes/quick-create', methods=['POST'])
def quick_create_promocode():
    """Быстрое создание промокода"""
    try:
        duration_seconds = int(request.form.get('duration_seconds', 0))
        max_activations = int(request.form.get('max_activations', 0))

        if duration_seconds <= 0 or max_activations <= 0:
            flash('Некорректные параметры промокода', 'error')
            return redirect(url_for('admin.promocodes_list'))

        # Генерируем случайный код
        def generate_random_code():
            prefixes = ['PROMO', 'BONUS', 'GIFT', 'FREE', 'VIP']
            prefix = random.choice(prefixes)
            suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            return f"{prefix}{suffix}"

        # Пытаемся создать уникальный код
        for _ in range(10):
            code = generate_random_code()
            success, message = SubscriptionService.create_promocode(code, duration_seconds, max_activations)
            if success:
                flash(f'Промокод {code} успешно создан', 'success')
                return redirect(url_for('admin.promocodes_list'))

        flash('Не удалось создать уникальный промокод', 'error')

    except Exception as e:
        logger.error(f"Ошибка быстрого создания промокода: {e}")
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('admin.promocodes_list'))


@admin_bp.route('/promocodes/bulk-create', methods=['POST'])
def bulk_create_promocodes():
    """Массовое создание промокодов"""
    try:
        count = int(request.form.get('count', 0))
        duration_seconds = int(request.form.get('duration_seconds', 0))
        max_activations = int(request.form.get('max_activations', 0))

        if count <= 0 or count > 100:
            flash('Количество промокодов должно быть от 1 до 100', 'error')
            return redirect(url_for('admin.promocodes_list'))

        if duration_seconds <= 0 or max_activations <= 0:
            flash('Некорректные параметры промокодов', 'error')
            return redirect(url_for('admin.promocodes_list'))

        # Генерируем промокоды
        created_count = 0
        failed_count = 0

        def generate_bulk_code(index):
            timestamp = datetime.now().strftime('%m%d')
            return f"BULK{timestamp}{index:03d}"

        for i in range(1, count + 1):
            code = generate_bulk_code(i)
            success, message = SubscriptionService.create_promocode(code, duration_seconds, max_activations)
            if success:
                created_count += 1
            else:
                failed_count += 1
                logger.warning(f"Не удалось создать промокод {code}: {message}")

        if created_count > 0:
            flash(f'Создано {created_count} промокодов', 'success')

        if failed_count > 0:
            flash(f'Не удалось создать {failed_count} промокодов', 'warning')

    except Exception as e:
        logger.error(f"Ошибка массового создания промокодов: {e}")
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('admin.promocodes_list'))


@admin_bp.route('/promocodes/<int:promocode_id>/toggle', methods=['POST'])
def toggle_promocode_status(promocode_id):
    """Переключение статуса промокода"""
    try:
        success, message = SubscriptionService.toggle_promocode_status(promocode_id)

        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "error": message}), 400

    except Exception as e:
        logger.error(f"Ошибка переключения статуса промокода {promocode_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/promocodes/<int:promocode_id>/details')
def promocode_details(promocode_id):
    """Получение детальной информации о промокоде"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Получаем промокод
            cursor.execute("SELECT * FROM promocodes WHERE id = ?", (promocode_id,))
            promocode = cursor.fetchone()

            if not promocode:
                return jsonify({"success": False, "error": "Промокод не найден"}), 404

            promocode = dict(promocode)
            promocode['duration_human'] = seconds_to_human_readable(promocode['duration_seconds'])
            promocode['created_at'] = promocode['created_at'].strftime('%d.%m.%Y %H:%M:%S')

            # Получаем историю активаций
            cursor.execute("""
                SELECT u.telegram_id as user_telegram_id, pa.activated_at
                FROM promocode_activations pa
                JOIN users u ON pa.user_id = u.id
                WHERE pa.promocode_id = ?
                ORDER BY pa.activated_at DESC
                LIMIT 100
            """, (promocode_id,))

            activations = []
            for row in cursor.fetchall():
                activation = dict(row)
                activation['activated_at'] = activation['activated_at'].strftime('%d.%m.%Y %H:%M:%S')
                activations.append(activation)

        return jsonify({
            "success": True,
            "promocode": promocode,
            "activations": activations
        })

    except Exception as e:
        logger.error(f"Ошибка получения деталей промокода {promocode_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/promocodes/<int:promocode_id>/delete', methods=['POST'])
def delete_promocode(promocode_id):
    """Удаление промокода"""
    try:
        success, message = SubscriptionService.delete_promocode(promocode_id)

        if success:
            flash(f'Промокод удален: {message}', 'success')
        else:
            flash(f'Ошибка удаления: {message}', 'error')

    except Exception as e:
        logger.error(f"Ошибка удаления промокода {promocode_id}: {e}")
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('admin.promocodes_list'))


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ОБРАБОТЧИКИ ОШИБОК
# ============================================================================

@admin_bp.errorhandler(404)
def not_found_error(error):
    flash('Страница не найдена', 'error')
    return redirect(url_for('admin.index'))


@admin_bp.errorhandler(500)
def internal_error(error):
    logger.error(f"Внутренняя ошибка: {error}")
    flash('Произошла внутренняя ошибка сервера', 'error')
    return redirect(url_for('admin.index'))


# Контекстные процессоры для шаблонов
@admin_bp.context_processor
def utility_processor():
    """Добавляем полезные функции в контекст шаблонов"""
    return {
        'datetime': datetime,
        'timedelta': timedelta,
        'seconds_to_human_readable': seconds_to_human_readable,
        'current_time': datetime.now()
    }