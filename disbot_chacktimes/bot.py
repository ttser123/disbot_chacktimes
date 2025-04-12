import discord
from discord.ext import commands, tasks
import os
import time
import json
import asyncio
from dotenv import load_dotenv
from datetime import datetime

# โหลด Token จากไฟล์ .env
load_dotenv()

# ตั้งค่าเส้นทางข้อมูล
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# ตั้งค่า Intents
intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.message_content = True

# สร้าง instance ของ Bot พร้อม prefix และ intents
bot = commands.Bot(command_prefix='!', intents=intents)

# สำหรับเก็บข้อมูลสถิติการใช้งานห้องเสียง
voice_time = {}    
# สำหรับเก็บ ID ของข้อความ realtime ที่ถูกสร้างไว้
realtime_messages = {}
# สำหรับเก็บ task ของการอัปเดตข้อความ realtime
realtime_tasks = {}

# เก็บเวลา startup ของบอท เพื่อใช้ในคำสั่ง uptime
startup_time = time.time()

# ID ของช่อง log ที่จะส่งข้อความแจ้งเตือน
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID'))

# ตัวแปรเพื่อป้องกันการรัน on_ready ซ้ำ
on_ready_called = False

# ================= ระบบไฟล์ข้อมูล =================
def save_data():
    """บันทึกข้อมูลลงไฟล์ JSON"""
    try:
        file_path = os.path.join(DATA_DIR, 'voice_time.json')
        temp_path = file_path + '.tmp'
        
        # แปลงข้อมูลให้พร้อมบันทึก
        save_data_dict = {}
        for guild_id in voice_time:
            save_data_dict[guild_id] = {}
            for user_id in voice_time[guild_id]:
                save_data_dict[guild_id][user_id] = {
                    'total_time': float(voice_time[guild_id][user_id]['total_time']),
                    'join_time': float(voice_time[guild_id][user_id]['join_time']) if voice_time[guild_id][user_id]['join_time'] else None
                }
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(save_data_dict, f, indent=2, ensure_ascii=False)
        
        if os.path.exists(file_path):
            os.remove(file_path)
        os.rename(temp_path, file_path)
        print(f"{datetime.now().strftime('%H:%M:%S')} 💾 บันทึกข้อมูลสำเร็จ!")
    except Exception as e:
        print(f"{datetime.now().strftime('%H:%M:%S')} ❌ บันทึกข้อมูลล้มเหลว: {e}")

def load_data():
    """โหลดข้อมูลจากไฟล์ JSON"""
    global voice_time
    file_path = os.path.join(DATA_DIR, 'voice_time.json')
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                voice_time = json.load(f)
            # แปลงข้อมูลให้ถูกประเภท
            for guild_id in voice_time:
                for user_id in voice_time[guild_id]:
                    voice_time[guild_id][user_id]['total_time'] = float(voice_time[guild_id][user_id]['total_time'])
                    voice_time[guild_id][user_id]['join_time'] = (
                        float(voice_time[guild_id][user_id]['join_time'])
                        if voice_time[guild_id][user_id]['join_time'] else None
                    )
            print(f"{datetime.now().strftime('%H:%M:%S')} 📂 โหลดข้อมูลสำเร็จ!")
        else:
            voice_time = {}
            print(f"{datetime.now().strftime('%H:%M:%S')} ⚠️ ไม่พบไฟล์ข้อมูล สร้างใหม่")
    except Exception as e:
        print(f"{datetime.now().strftime('%H:%M:%S')} ⚠️ ข้อผิดพลาดขณะโหลดข้อมูล: {e}")
        voice_time = {}

# ================= ฟังก์ชันอัปเดตข้อความเรียลไทม์ =================
async def update_realtime_message(channel, member, start_time):
    """
    อัปเดตข้อความแบบเรียลไทม์ในรูปแบบ:
    🎧 <display_name> อยู่ในห้อง: <channel_name> | เวลา: 0h 4m 14s
    """
    try:
        # ส่งข้อความเริ่มต้น
        message = await channel.send(f"🎧 {member.display_name} อยู่ในห้อง: {member.voice.channel.name} | เวลา: 0h 0m 0s")
        realtime_messages[member.id] = message

        while member.id in realtime_messages:
            elapsed = int(time.time() - start_time)
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            new_content = (f"🎧 {member.display_name} อยู่ในห้อง: {member.voice.channel.name} | "
                           f"เวลา: {hours}h {minutes}m {seconds}s")
            await message.edit(content=new_content)
            await asyncio.sleep(5)  # ปรับความถี่การอัปเดตได้ตามต้องการ
    except Exception as e:
        print(f"Error updating realtime message: {e}")

# ================= ระบบตรวจจับห้องเสียง =================
@bot.event
async def on_voice_state_update(member, before, after):
    # ข้ามหากเป็นบอท
    if member.bot:
        return

    guild_id = str(member.guild.id)
    user_id = str(member.id)

    # ========== บันทึกสถิติเวลา ==========
    if guild_id not in voice_time:
        voice_time[guild_id] = {}

    # เมื่อออกจากห้อง (หรือย้ายออกจากห้องเดิม)
    if before.channel:
        if user_id in voice_time[guild_id]:
            data = voice_time[guild_id][user_id]
            if data['join_time'] is not None:
                elapsed = time.time() - data['join_time']
                data['total_time'] += elapsed
                data['join_time'] = None
                print(f"{datetime.now().strftime('%H:%M:%S')} ⏳ {member.display_name} ใช้เวลา {elapsed:.2f}s")
    
    # เมื่อเข้าหรือย้ายเข้าห้องใหม่
    if after.channel:
        voice_time[guild_id][user_id] = {
            'total_time': voice_time[guild_id].get(user_id, {}).get('total_time', 0.0),
            'join_time': time.time()
        }

    # ========== จัดการข้อความเรียลไทม์ ==========
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    # กรณีเข้าห้องใหม่ (ไม่ใช่การย้าย)
    if after.channel and not before.channel:
        start_time = time.time()
        realtime_tasks[member.id] = asyncio.create_task(update_realtime_message(log_channel, member, start_time))
    # กรณีออกจากห้อง
    elif before.channel and not after.channel:
        if member.id in realtime_tasks:
            realtime_tasks[member.id].cancel()
            del realtime_tasks[member.id]
        if member.id in realtime_messages:
            message = realtime_messages.pop(member.id)
            # สรุปเวลาสุดท้าย (ใช้ join_time ที่บันทึกไว้)
            elapsed = int(time.time() - voice_time[guild_id][user_id]['join_time']) if voice_time[guild_id][user_id]['join_time'] else 0
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            final_content = (f"🎧 {member.display_name} อยู่ในห้อง: {before.channel.name} | "
                             f"เวลา: {hours}h {minutes}m {seconds}s")
            try:
                await message.edit(content=final_content)
            except Exception as e:
                print(f"Error editing final realtime message: {e}")
    # กรณีย้ายห้อง
    elif before.channel and after.channel:
        if member.id in realtime_tasks:
            realtime_tasks[member.id].cancel()
            del realtime_tasks[member.id]
        if member.id in realtime_messages:
            message = realtime_messages.pop(member.id)
            try:
                await message.edit(content=f"🎧 {member.display_name} อยู่ในห้อง: {before.channel.name}")
            except Exception as e:
                print(f"Error editing realtime message on channel change: {e}")
        start_time = time.time()
        realtime_tasks[member.id] = asyncio.create_task(update_realtime_message(log_channel, member, start_time))

# ================= ระบบเซฟอัตโนมัติ =================
@tasks.loop(minutes=30)
async def auto_save():
    save_data()
    print(f"{datetime.now().strftime('%H:%M:%S')} 🔄 เซฟข้อมูลอัตโนมัติ")

# ================= คำสั่งสำหรับแสดงสถิติ =================
@bot.command()
@commands.cooldown(1, 5, commands.BucketType.user)
async def topvoice(ctx):
    """แสดง 10 อันดับผู้ใช้ที่อยู่ในห้องเสียงนานที่สุด"""
    guild_id = str(ctx.guild.id)
    
    if not voice_time.get(guild_id):
        await ctx.send("⚠️ ยังไม่มีข้อมูล!")
        return

    rankings = []
    for user_id, data in voice_time[guild_id].items():
        try:
            total = data['total_time']
            if data['join_time'] is not None:
                total += time.time() - data['join_time']
            
            user = await bot.fetch_user(int(user_id))
            rankings.append((user.display_name, total))
        except Exception as e:
            print(f"⚠️ เกิดข้อผิดพลาดกับผู้ใช้ {user_id}: {e}")

    rankings.sort(key=lambda x: x[1], reverse=True)
    
    message = "🏆 **อันดับผู้ใช้ในห้องเสียง**\n"
    for i, (user, total) in enumerate(rankings[:10], 1):
        hours = int(total // 3600)
        minutes = int((total % 3600) // 60)
        seconds = int(total % 60)
        message += f"{i}. {user} - {hours}h {minutes}m {seconds}s\n"
    
    await ctx.send(message)

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.user)
async def mytime(ctx):
    """แสดงเวลาที่คุณอยู่ในห้องเสียง"""
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)
    
    if not voice_time.get(guild_id, {}).get(user_id):
        await ctx.send("⚠️ ยังไม่มีข้อมูลของคุณ!")
        return
    
    data = voice_time[guild_id][user_id]
    total = data['total_time']
    if data['join_time'] is not None:
        total += time.time() - data['join_time']
    
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    seconds = int(total % 60)
    await ctx.send(f"⏳ เวลาของคุณ: {hours}h {minutes}m {seconds}s")

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.user)
async def save(ctx):
    """บันทึกข้อมูลทันที (เฉพาะผู้ดูแล)"""
    if ctx.author.guild_permissions.administrator:
        save_data()
        await ctx.send("💾 บันทึกข้อมูลเรียบร้อย!")
    else:
        await ctx.send("⛔ คุณไม่มีสิทธิ์ใช้งานคำสั่งนี้!")

# คำสั่งเพิ่มเติมเจ๋ง ๆ

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.user)
async def ping(ctx):
    """เช็คการตอบสนองของบอท (Latency)"""
    latency = bot.latency * 1000  # แปลงเป็นมิลลิวินาที
    await ctx.send(f"🏓 Pong! Latency: {latency:.0f} ms")

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.user)
async def uptime(ctx):
    """แสดงระยะเวลา uptime ของบอท"""
    elapsed = int(time.time() - startup_time)
    hours = elapsed // 3600
    minutes = (elapsed % 3600) // 60
    seconds = elapsed % 60
    await ctx.send(f"🚀 Uptime: {hours}h {minutes}m {seconds}s")

@bot.command()
@commands.cooldown(1, 10, commands.BucketType.guild)
async def reset(ctx):
    """รีเซ็ตสถิติการใช้งานห้องเสียง (เฉพาะผู้ดูแล)"""
    if ctx.author.guild_permissions.administrator:
        guild_id = str(ctx.guild.id)
        voice_time[guild_id] = {}
        save_data()
        await ctx.send("🔄 สถิติถูกรีเซ็ตแล้ว!")
    else:
        await ctx.send("⛔ คุณไม่มีสิทธิ์ใช้งานคำสั่งนี้!")

# ================= เริ่มต้นและ event ต่าง ๆ =================
@bot.event
async def on_ready():
    global on_ready_called
    if on_ready_called:
        return
    on_ready_called = True
    load_data()
    auto_save.start()
    print(f"{datetime.now().strftime('%H:%M:%S')} ✅ {bot.user} เริ่มทำงานแล้ว!")

@bot.event
async def on_disconnect():
    save_data()

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))
