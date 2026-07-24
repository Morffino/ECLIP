import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
import os
import sys

# ============================================
# ВАШИ ДАННЫЕ (уже вставлены)
# ============================================
TOKEN = "MTUzMDAwMTkxNzMxNTM4NzQ2Mw.G2hmPV.EgzMmNf4rQw0iYtR45gh173SLSIrRZyE292jBI"
GUILD_ID = 1528337219612311633
CATEGORY_ID = 1529240936356380672
STAFF_ROLE_ID = 1529251785678655589
LOG_CHANNEL_ID = 1530014247898054799
TICKET_LIFETIME_HOURS = 10
# ============================================

# Настройка интентов
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree

# Хранилище тикетов
tickets = {}

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📋 Общие вопросы", style=discord.ButtonStyle.primary, custom_id="general", emoji="📋")
    async def general_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Общие вопросы")
    
    @discord.ui.button(label="🔄 Восстановление вещей", style=discord.ButtonStyle.success, custom_id="restore", emoji="🔄")
    async def restore_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Восстановление вещей")
    
    @discord.ui.button(label="⚙️ Технические проблемы", style=discord.ButtonStyle.secondary, custom_id="tech", emoji="⚙️")
    async def tech_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Технические проблемы")
    
    @discord.ui.button(label="⚠️ Жалоба на игрока", style=discord.ButtonStyle.danger, custom_id="player", emoji="⚠️")
    async def player_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Жалоба на игрока")
    
    @discord.ui.button(label="👑 Жалоба на Администрацию", style=discord.ButtonStyle.danger, custom_id="admin", emoji="👑")
    async def admin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Жалоба на Администрацию")
    
    async def create_ticket(self, interaction: discord.Interaction, topic: str):
        # Проверка на существующий тикет
        for ticket in tickets.values():
            if ticket['user_id'] == interaction.user.id and ticket['status'] == 'open':
                await interaction.response.send_message("❌ У вас уже есть открытый тикет!", ephemeral=True)
                return
        
        guild = interaction.guild
        category = discord.utils.get(guild.categories, id=CATEGORY_ID)
        
        if not category:
            await interaction.response.send_message("❌ Категория для тикетов не найдена!", ephemeral=True)
            return
        
        # Создание канала
        ticket_number = len([t for t in tickets.values() if t['status'] == 'open']) + 1
        channel_name = f"ticket-{interaction.user.name.lower()}-{ticket_number}"
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        
        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Тикет от {interaction.user.name} - {topic}"
        )
        
        # Сохранение тикета
        tickets[channel.id] = {
            'user_id': interaction.user.id,
            'user_name': interaction.user.name,
            'topic': topic,
            'status': 'open',
            'created_at': datetime.now().isoformat(),
            'closing_time': (datetime.now() + timedelta(hours=TICKET_LIFETIME_HOURS)).isoformat()
        }
        
        # Отправка сообщения
        embed = discord.Embed(
            title="🎫 HS TICKET | Центр поддержки",
            description=f"Тикет создан по теме: **{topic}**",
            color=0x00ff00
        )
        embed.add_field(name="🆔 Укажите SteamID64", value="https://steamid.io", inline=False)
        embed.add_field(name="👤 Ваш ник в игре", value="Укажите игровой ник", inline=False)
        embed.add_field(name="📝 Кратко о проблеме", value="До 30 символов", inline=False)
        embed.add_field(name="⏰ Авто-закрытие", value=f"Через {TICKET_LIFETIME_HOURS} часов", inline=False)
        embed.set_footer(text=f"Создан: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        
        view = TicketControlView()
        staff_role = guild.get_role(STAFF_ROLE_ID)
        await channel.send(
            f"{interaction.user.mention} {staff_role.mention if staff_role else ''}",
            embed=embed,
            view=view
        )
        
        # Запуск таймера
        bot.loop.create_task(auto_close_ticket(channel.id))
        
        # Логирование
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="📩 Создан новый тикет",
                description=f"👤 {interaction.user.mention}\n📂 {topic}\n📌 {channel.mention}",
                color=0x00ff00,
                timestamp=datetime.now()
            )
            await log_channel.send(embed=log_embed)
        
        await interaction.response.send_message(f"✅ Тикет создан! Перейдите в {channel.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="❌ Закрыть", style=discord.ButtonStyle.danger, custom_id="close", emoji="❌")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(STAFF_ROLE_ID):
            await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id not in tickets:
            await interaction.response.send_message("❌ Тикет не найден!", ephemeral=True)
            return
        
        await close_ticket(channel, interaction.user, "Закрыт персоналом")
        await interaction.response.send_message("🔄 Тикет закрывается...")
    
    @discord.ui.button(label="⏰ Продлить", style=discord.ButtonStyle.primary, custom_id="extend", emoji="⏰")
    async def extend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(STAFF_ROLE_ID):
            await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id not in tickets:
            await interaction.response.send_message("❌ Тикет не найден!", ephemeral=True)
            return
        
        tickets[channel.id]['closing_time'] = (datetime.now() + timedelta(hours=TICKET_LIFETIME_HOURS)).isoformat()
        embed = discord.Embed(title="⏰ Тикет продлен", description=f"На {TICKET_LIFETIME_HOURS} часов", color=0x00ff00)
        await channel.send(embed=embed)
        await interaction.response.send_message("✅ Тикет продлен!", ephemeral=True)

async def auto_close_ticket(channel_id):
    await asyncio.sleep(TICKET_LIFETIME_HOURS * 3600)
    
    if channel_id not in tickets or tickets[channel_id]['status'] != 'open':
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    
    embed = discord.Embed(title="⏰ Авто-закрытие", description="Через 60 секунд", color=0xff0000)
    await channel.send(embed=embed)
    await asyncio.sleep(60)
    
    if channel_id not in tickets or tickets[channel_id]['status'] != 'open':
        return
    
    await close_ticket(channel, bot.user, "Автоматическое закрытие")

async def close_ticket(channel, closer, reason):
    if channel.id not in tickets:
        return
    
    ticket_info = tickets[channel.id]
    
    # Сбор сообщений
    messages = []
    async for msg in channel.history(limit=200, oldest_first=True):
        messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content[:100]}")
    
    # Логирование
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(
            title="📪 Тикет закрыт",
            description=f"👤 {ticket_info['user_name']}\n📂 {ticket_info['topic']}\n🔒 {closer.name if hasattr(closer, 'name') else 'Auto'}\n📝 {reason}",
            color=0xff0000,
            timestamp=datetime.now()
        )
        await log_channel.send(embed=embed)
        
        # Сохранение лога
        log_text = f"=== ЛОГ ТИКЕТА ===\n{ticket_info['created_at']}\n{ticket_info['user_name']}\n{ticket_info['topic']}\n========================\n\n"
        log_text += "\n".join(messages)
        
        filename = f"ticket_log_{channel.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(log_text)
        await log_channel.send(file=discord.File(filename))
        os.remove(filename)
    
    del tickets[channel.id]
    await channel.delete()

# ============ СЛЕШ-КОМАНДЫ ============

@tree.command(name="setup", description="📌 Создать кнопки для тикетов")
@app_commands.default_permissions(administrator=True)
async def slash_setup(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Добро пожаловать",
        description="Выберите тему обращения:",
        color=0x3498db
    )
    embed.add_field(
        name="📌 Информация",
        value=f"⏰ Закрытие через {TICKET_LIFETIME_HOURS} ч\n👥 <@&{STAFF_ROLE_ID}>",
        inline=False
    )
    await interaction.response.send_message(embed=embed, view=TicketView())

@tree.command(name="stats", description="📊 Статистика тикетов")
@app_commands.default_permissions(administrator=True)
async def slash_stats(interaction: discord.Interaction):
    open_count = len([t for t in tickets.values() if t['status'] == 'open'])
    embed = discord.Embed(title="📊 Статистика", color=0x3498db)
    embed.add_field(name="🟢 Открыто", value=open_count, inline=True)
    embed.add_field(name="📋 Всего", value=len(tickets), inline=True)
    await interaction.response.send_message(embed=embed)

@tree.command(name="close", description="❌ Закрыть текущий тикет")
@app_commands.default_permissions(administrator=True)
async def slash_close(interaction: discord.Interaction):
    channel = interaction.channel
    if channel.id not in tickets:
        await interaction.response.send_message("❌ Это не тикет!", ephemeral=True)
        return
    await close_ticket(channel, interaction.user, "Команда /close")
    await interaction.response.send_message("🔄 Закрытие...")

@tree.command(name="extend", description="⏰ Продлить текущий тикет")
@app_commands.default_permissions(administrator=True)
async def slash_extend(interaction: discord.Interaction):
    channel = interaction.channel
    if channel.id not in tickets:
        await interaction.response.send_message("❌ Это не тикет!", ephemeral=True)
        return
    
    tickets[channel.id]['closing_time'] = (datetime.now() + timedelta(hours=TICKET_LIFETIME_HOURS)).isoformat()
    embed = discord.Embed(title="⏰ Тикет продлен", description=f"На {TICKET_LIFETIME_HOURS} часов", color=0x00ff00)
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Тикет продлен!", ephemeral=True)

@tree.command(name="help", description="🆘 Помощь по командам")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="🆘 Команды", color=0x3498db)
    embed.add_field(
        name="📋 Список команд",
        value=(
            "**👤 Для всех:**\n"
            "`/help` - Помощь\n\n"
            "**👥 Для персонала:**\n"
            "`/close` - Закрыть тикет\n"
            "`/extend` - Продлить тикет\n\n"
            "**🛠️ Для администраторов:**\n"
            "`/setup` - Создать кнопки\n"
            "`/stats` - Статистика"
        ),
        inline=False
    )
    embed.set_footer(text=f"Тикеты живут {TICKET_LIFETIME_HOURS} часов")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============ СОБЫТИЯ ============

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"✅ Бот запущен: {bot.user}")
    print(f"🆔 ID бота: {bot.user.id}")
    print(f"📊 На серверах: {len(bot.guilds)}")
    
    # Установка статуса
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(type=discord.ActivityType.watching, name="тикеты | /help")
    )
    
    # Синхронизация команд
    try:
        synced = await tree.sync()
        print(f"✅ Синхронизировано {len(synced)} команд:")
        for cmd in synced:
            print(f"   • /{cmd.name} - {cmd.description}")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
    
    # Проверка каналов
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f"\n📌 Сервер: {guild.name}")
        
        # Проверка канала #tickets
        ticket_channel = discord.utils.get(guild.text_channels, name="tickets")
        if ticket_channel:
            print(f"✅ Канал #tickets найден: {ticket_channel.name}")
            
            # Очистка старых сообщений
            try:
                async for msg in ticket_channel.history(limit=100):
                    if msg.author == bot.user:
                        await msg.delete()
                print("   🧹 Старые сообщения очищены")
            except:
                pass
            
            # Создание нового сообщения
            embed = discord.Embed(
                title="🎫 Добро пожаловать",
                description="Нажмите на кнопку для создания тикета",
                color=0x3498db
            )
            embed.add_field(
                name="📌 Информация",
                value=(
                    f"⏰ **Авто-закрытие:** через {TICKET_LIFETIME_HOURS} часов\n"
                    f"👥 **Персонал:** <@&{STAFF_ROLE_ID}>\n"
                    f"📋 **Выберите тему обращения:**"
                ),
                inline=False
            )
            embed.set_footer(text="Система тикетов v2.0")
            
            await ticket_channel.send(embed=embed, view=TicketView())
            print("✅ Сообщение создано в #tickets")
        else:
            print("⚠️ Канал #tickets не найден! Создайте канал с таким именем.")
        
        # Проверка канала логов
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            print(f"✅ Канал логов найден: {log_channel.name}")
        else:
            print(f"⚠️ Канал логов (ID: {LOG_CHANNEL_ID}) не найден!")
    else:
        print(f"⚠️ Сервер с ID {GUILD_ID} не найден!")
    
    print("=" * 60)
    print("🚀 Бот готов к работе!")
    print("=" * 60)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if message.channel.id in tickets:
        tickets[message.channel.id]['last_message'] = datetime.now().isoformat()
    
    await bot.process_commands(message)

@bot.event
async def on_error(event, *args, **kwargs):
    print(f"❌ Ошибка: {event}")

# ============ ЗАПУСК ============

if __name__ == "__main__":
    print("🚀 Запуск бота...")
    print(f"📌 Сервер ID: {GUILD_ID}")
    print(f"📌 Категория ID: {CATEGORY_ID}")
    print(f"📌 Роль персонала ID: {STAFF_ROLE_ID}")
    print(f"📌 Канал логов ID: {LOG_CHANNEL_ID}")
    print(f"⏰ Время жизни: {TICKET_LIFETIME_HOURS} часов")
    print("=" * 60)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Ошибка: Неправильный токен!")
        print("💡 Проверьте токен в переменной TOKEN")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
