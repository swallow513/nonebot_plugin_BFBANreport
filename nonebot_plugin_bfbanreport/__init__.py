from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot_plugin_BFBANreport",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

import requests
import base64
import aiohttp
import asyncio
from nonebot import require
from typing import Any, Dict, Optional
from nonebot.params import ArgPlainText
from nonebot.typing import T_State
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent,MessageEvent,Event, Message, MessageSegment
from nonebot.params import Arg, ArgPlainText, CommandArg, Received
from nonebot import on_command

require("nonebot_plugin_htmlrender")
from nonebot_plugin_htmlrender import (
    html_to_pic,
    text_to_pic,
    md_to_pic,
)
status_descriptions = {
    0: "未处理", 1: "石锤", 2: "待自证", 3: "MOSS自证", 4: "无效举报",
    5: "讨论中", 6: "等待确认", 7: "空", 8: "刷枪", 9: "上诉", 'None': "无记录", 'null': "无记录",
}
HEADERS = {
    "Content-Type": "application/json",
    "x-access-token": token
}


# 获取ban数据
async def checkban(session: aiohttp.ClientSession, username: str) -> Optional[Dict[str, Any]]:
    url_all = f"https://api.bfban.com/api/search?param={username}&type=player&scope=current&limit=6"
    data = await fetch_json(session, url_all)
    return data


# 检查用户数据
async def get_persona_id(session: aiohttp.ClientSession, username: str) -> Optional[str]:
    url_uid = f"https://api.bfvrobot.net/api/v2/bfv/checkPlayer?name={username}"
    user_data = await fetch_json(session, url_uid)
    if user_data and user_data.get("status") == 1 and user_data.get("message") == "successful":
        return user_data
    return None


# 获取验证码
async def get_captcha():
    """获取验证码"""
    response = requests.get("https://api.bfban.com/api/captcha")
    if response.status_code == 200:
        data = response.json()
        if data["success"] == 1:
            return data["data"]["hash"], data["data"]["content"]
    return None, None


# 转图片发送
def create_html(data_uri: str) -> str:
    """生成嵌入了验证码的 HTML"""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Captcha</title>
        <style>
            body, html {{
                margin: 0;
                padding: 0;
                width: 240px;
                height: 120px;
                display: flex;
                justify-content: center;
                align-items: center;
                background-color: #ffffff;
            }}
            img {{
                width: 240px;
                height: 120px;
                object-fit: cover;
            }}
        </style>
    </head>
    <body>
        <img src="{data_uri}" alt="Captcha">
    </body>
    </html>
    """


# 异步请求 JSON 数据
async def fetch_json(session: aiohttp.ClientSession, url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    try:
        async with session.get(url, timeout=timeout) as response:
            if response.status == 200:
                return await response.json()
            else:
                return None
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        return None


# 上传至图床
def upload_image(image_path):
    url = "https://img.api.aa1.cn/api/upload"
    with open(image_path, 'rb') as image_file:
        files = {'image': image_file}
        response = requests.post(url, files=files)
        if response.status_code == 200:
            data = response.json()
            if data['code'] == 200:
                url = f"""<img src="{data['data']['url']}" alt="{data['data']['name']}" title="{data['data']['name']}" />"""
                return url
            else:
                return None
        else:
            return None


# 举报用户
async def report_player(session, origin_name, game, cheat_methods, video_link, description, captcha, encrypt_captcha):
    """举报玩家"""
    body = {
        "data": {
            "game": game,
            "originName": origin_name,
            "cheatMethods": cheat_methods,
            "videoLink": video_link,
            "description": description
        },
        "encryptCaptcha": encrypt_captcha,
        "captcha": captcha
    }

    # 更新请求的 API 地址
    async with session.post("https://api.bfban.com/api/player/report", headers=HEADERS, json=body) as response:
        # 直接返回响应内容
        return await response.json()


# 隐藏资料
def mask_id(id_number, masked_length):
    # 将数字转换为字符串
    id_str = str(id_number)

    # 获取ID的总长度
    total_length = len(id_str)

    # 确保ID长度和需要隐藏的长度是合理的
    if total_length <= masked_length:
        raise ValueError("ID length must be greater than masked length.")

    # 计算需要显示的前缀长度
    prefix_length = total_length - masked_length

    # 生成掩码后的字符串
    masked_id = id_str[:prefix_length] + '*' * masked_length
    return masked_id


# 定义举报指令
report = on_command(".report",aliases={'。report', '.举报', '。举报'})


# 定义初始处理函数
@report.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State,args: Message = CommandArg()):
    user_id = args.extract_plain_text().strip()
    await report.send("正在获取玩家数据,请稍后 >>>>>")
    find = False
    async with aiohttp.ClientSession() as session:
        user_data = await get_persona_id(session, user_id)
        try:
            persona_id = user_data["data"]["personaId"]
        except TypeError:
            await report.finish("玩家未找到,请检查ID后重试!")
        data = await checkban(session=session,username=user_id)
        try:
            stat = data["message"]
        except KeyError:
            find = True
            url = data["data"][0]["originPersonaId"]
            status = data["data"][0]["status"]
            status_descrip = status_descriptions.get(status,"未知")
            await report.send(f"!请注意, 该玩家已经在BFBAN存在案件:\nBFBAN状态:{status_descrip}\nhttps://bfban.com/player/{url}\n如需继续举报补充证据请输入需要举报的游戏类型(支持1和5), 取消举报请发送'取消'")
    state["origin_name"] = user_id
    if not find:
        await report.send(message="请输入游戏名称(支持1和5)\n或输入 '取消' 以结束操作：")


# 获取游戏名称
@report.got("game")
async def handle_game(bot: Bot, event: MessageEvent, state: T_State):
    game_input = event.get_message().extract_plain_text().strip().lower()
    if game_input == '取消':
        await report.finish("操作已取消")
    if game_input in ['1', '战地1', 'bf1']:
        state["game"] = "bf1"
    elif game_input in ['5', '战地五', 'bfv']:
        state["game"] = "bfv"
    else:
        await report.send(
            "游戏名称不支持，请重新输入有效的游戏名称(支持1或5)\n或输入 '取消' 以结束操作：")
        # 使用 reject 让用户重新输入游戏类型
        await report.reject()
    state["cheat_methods"] = ['aimbot']
    state["video_link"] = None
    await report.send(message="请上传图片(可选，输入'无'表示不提供)\n或输入 '取消' 以结束操作：")


# 上传图片
@report.got("picture_link")
async def handle_picture_link(bot: Bot, event: MessageEvent, state: T_State):
    img = str(event.get_message()).strip().lower()
    if img == '取消':
        await report.finish("操作已取消")
    if img == '无':
        state["picture_link"] = None
    else:
        parts = img.split(',')
        file_id = None
        for part in parts:
            if part.startswith("file="):
                file_id = part.split('=')[1]
        if file_id:
            try:
                data = await bot.call_api("get_image", file=file_id)
                file_path = data['file']
                picture_link = upload_image(file_path)
                await report.send("图片上传成功!")
                state["picture_link"] = picture_link
            except Exception as e:
                await report.send(f"图片上传失败,请重试\n或输入'无'表示不提供图片,输入'取消'以结束操作：")
                # 使用 reject 让用户重新上传图片
                await report.reject()
        else:
            await report.send("未找到有效的文件,请重新上传图片\n或输入'无'表示不提供,输入'取消'以结束操作：")
            # 使用 reject 让用户重新上传图片
            await report.reject()
    await report.send("请输入举报的详细信息\n视频请先上传至bilibili等网站后, 再回复视频链接.不要将视频上传至网盘!请不要在没有客观证据下凭借主观意识随意举报! \n或输入'取消'以结束操作：")


# 获取描述
@report.got("description")
async def handle_description(bot: Bot, event: MessageEvent, state: T_State):
    description = event.get_message().extract_plain_text()
    if description.lower() == '取消':
        await report.finish("操作已取消")
    state["description"] = description
    # 获取验证码
    hash_value, svg_content = await get_captcha()
    if hash_value and svg_content:
        svg_data_encoded = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')
        data_uri = f"data:image/svg+xml;base64,{svg_data_encoded}"
        html_content = create_html(data_uri)
        viewport = {"width": 240, "height": 120}
        pic = await html_to_pic(html_content, wait=2, type="png", device_scale_factor=2, **{"viewport": viewport})
        await report.send(MessageSegment.image(pic))
        state["captcha_hash"] = hash_value
        # 询问用户输入验证码
        await report.send(message="请输入验证码，或输入 '取消' 以结束操作：")
    else:
        await report.finish("获取验证码失败，请稍后再试")

# 定义获取验证码输入后的处理器
@report.got("captcha_input")
async def handle_captcha_input(bot: Bot, event: GroupMessageEvent, state: T_State):
    captcha_input = event.get_message().extract_plain_text()
    captcha_hash = state["captcha_hash"]
    groupid = mask_id(event.group_id,5)
    userid = mask_id(event.user_id,5)
    header = f"<p>来自QQ群的举报<br>User ID: {userid}, Group ID: {groupid}<br><br>以下为用户提交的描述：<br></p>"
    async with aiohttp.ClientSession() as session:
        origin_name = state["origin_name"]
        game = state["game"]
        cheat_methods = state["cheat_methods"]
        video_link = None
        picture_link = state["picture_link"]
        description = state["description"]
        if picture_link is not None:
            content = f"{header}{picture_link}<p>{description}</p>"
        else:
            content = f"{header}<p>{description}</p>"
        # 调用举报函数
        response = await report_player(
            session,
            origin_name,
            game,
            cheat_methods,
            video_link,
            content,
            captcha_input,
            captcha_hash
        )
    if isinstance(response, dict):
        if response.get("error") == 1:
            if response.get("code") == "report.notFound":
                await report.reject("被举报者未找到，请确认 ID。")
            elif response.get("code") == "captcha.wrong":
                await report.reject("验证码错误，请重新输入：")
            else:
                await report.reject("举报失败，错误信息：" + response.get("message", "未知错误"))
        else:
            url = response["data"]["originPersonaId"]
            await report.finish(f"举报成功!案件链接:\nhttps://bfban.com/player/{url}")
    else:
        await report.reject("举报失败，返回的数据格式不正确。")

