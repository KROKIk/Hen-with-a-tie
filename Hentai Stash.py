import urllib.parse
import discord
from discord.ext import commands, tasks
import requests
from discord.utils import get
import asyncio
import mysql.connector
import re


# Connect to the mysql database
db = mysql.connector.connect(
  host="",
  user="",
  password=",
  database="hentaistash"
)

# Prepare the database
cursor = db.cursor()
cursor.execute("USE hentaistash")


# Configure bot permissions and prefix
intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Default request header
head = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:85.0) Gecko/20100101 Firefox/85.0"}


# Check if channel is a DM
async def check(channel):
    if channel.type is discord.ChannelType.private:
        return True
    return False


# Check if user is not registered
def is_not_registered(ctx):
    for role in ctx.author.roles:
        if role.name == "Degenerate":
            return False
    return True


# Startup function
@client.event
async def on_ready():
    print("Bot ready")
    msg = await client.get_channel(812341203630555156).history(limit=1).flatten()
    print(msg[0].reactions)


# Logic containing reaction controls
@client.event
async def on_raw_reaction_add(payload):
    # Ignore Bot reactions
    if payload.user_id == 811625796909006908:
        return

    # Fetch message that has been reacted to
    message = await client.get_channel(payload.channel_id).fetch_message(payload.message_id)
    reaction_channel = await client.fetch_channel(message.channel.id)
    reaction_category_name = reaction_channel.category.name

    # Break if user is not registered
    guild = client.guilds[0]
    member = await guild.fetch_member(payload.user_id)
    for role in member.roles:
        if role.name == "Guest":
            await message.remove_reaction(payload.emoji, payload.member)
            return

    # Download user credentials from database
    cursor.execute(f"SELECT * FROM credentials WHERE discord_id ='{payload.user_id}'")
    cred = cursor.fetchall()[0]

    # Create cookies
    cookies = {"user_id": cred[1], "pass_hash": cred[2]}

    # Get image id from the database
    cursor.execute(f"SELECT image_id FROM images WHERE image_link ='{message.content}'")

    # regex
    url = re.compile("https://img\d.gelbooru.com/images/")

    # TODO better solution
    try:
        image_id = cursor.fetchall()[0][0]
    except Exception:
        image_id = "0"

    # Reaction controls, ignores the non image channels
    if not reaction_category_name == "settings and help":

        # Add image to #favourites
        if payload.emoji.name == "add_fav":

            # Check if message is a link
            if re.match(url, message.content[:33]):

                # If image is on #removed remove it
                if message.channel.name == "removed" and message.channel.category.name == cred[3]:

                    # Delete message from the removed channel
                    await message.delete()

                # Add to favourites
                requests.get(f"https://gelbooru.com/public/addfav.php?id={image_id}", headers=head, cookies=cookies) # 1 = Already in favourites 2 = Not Logged in 3 = Success

                # Upvote
                requests.get(f"https://gelbooru.com/index.php?page=post&s=vote&id={image_id}&type=up", headers=head, cookies=cookies)

                # Update Favourites
                await download_favourites(user=cred, limit=50)

        # Remove image from #favouriyes and add it to #removed
        elif payload.emoji.name == "rem_fav":

            # remove from #favourites channel
            if re.match(url, message.content[:33]) and message.channel.name == "favourites" and message.channel.category.name == cred[3]:

                # Delete image from the channel
                await message.delete()

                # #remove channel
                channel = get(get(client.guilds[0].categories, name=cred[3]).text_channels, name="removed")

                # Fetched reactions
                add_fav = await client.guilds[0].fetch_emoji(812687578205257768)
                rem_fav = await client.guilds[0].fetch_emoji(812687316815839262)

                # Send the image to the removed channel to confirm deletion
                mes = await channel.send(message.content)
                await mes.add_reaction(add_fav)
                await mes.add_reaction(rem_fav)

                # Remove image from favourites on Gelbooru
                requests.get(f"https://gelbooru.com/index.php?page=favorites&s=delete&id={image_id}", headers=head, cookies=cookies)

                # Remove image from database
                cursor.execute(f"update sent set `{reaction_channel.id}` = NULL where `{reaction_channel.id}` = '{image_id}'")
                db.commit()

            elif re.match(url, message.content[:33]) and message.channel.name == "removed" and message.channel.category.name == cred[3]:
                await message.delete()

            # if reaction is not on a proper channel remove it
            else:
                await message.remove_reaction(payload.emoji, payload.member)

        # Send info on DM
        elif payload.emoji.name == "image_details":
            if re.match(url, message.content[:33]):

                # Code clarity
                user = await client.fetch_user(payload.user_id)
                dm = await user.create_dm()
                url = f"https://gelbooru.com/index.php?page=post&s=view&id={image_id})"
                r = requests.get(url, headers=head, cookies=cookies).text

                # Fetch tags
                t = r[r.find("<b>Tag</b>"):r.find("<h3>Statistics</h3>")]
                tags = [tag[tag.find("\">") + 2:] for tag in t.split("</a>") if t.split("</a>").index(tag) % 2 == 1]

                # Fetch artist
                artist = r[r.find('"tag-type-artist"'):]
                artist = artist[artist.find("</span>") + 7: artist[artist.find("</span>"):].find("</a>") + artist.find("</span>")]
                artist = artist[artist.find("\">") + 2:]
                if artist == "":
                    artist = "Artist Unknown"

                # Fetch character/s
                characters_raw = [m.start() for m in re.finditer('"tag-type-character"', r)]
                characters = []
                for character in characters_raw:
                    character = r[character:character + 300]
                    character = character[character.find("</span>"):]
                    character = character[:character.find("</a>")]
                    character = character[character.find("\">") + 2:]
                    characters.append(character)
                    if artist == "":
                        artist = "Character Unknown"

                # Fetch copyrights
                copyrights_raw = [m.start() for m in re.finditer('"tag-type-copyright"', r)]
                copyrights = []
                for cop in copyrights_raw:
                    cop = r[cop:cop + 300]
                    cop = cop[cop.find("</span>"):]
                    cop = cop[:cop.find("</a>")]
                    cop = cop[cop.find("\">") + 2:]
                    cop.append(cop)
                    if artist == "":
                        artist = "No copyrights"

                # Prepare strings
                characters_str = ""
                for character in characters:
                    characters_str += f"{character}, "
                characters_str = characters_str[:-2]

                tags_str = ""
                for tag in tags:
                    tags_str += f"{tag}, "
                tags_str = tags_str[:-2]

                copyrights_str = ""
                for cop in copyrights:
                    copyrights_str += f"{cop}, "
                copyrights_str += copyrights_str[:-2]

                embed = discord.Embed()
                embed.set_image(url=message.content)
                embed.description = f"Image Link: https://gelbooru.com/index.php?page=post&s=view&id={image_id}\n\nArtist: {artist}\n\nCharacter(s): {characters_str}\n\nCopyright: {copyrights_str}\n\nTags: {tags_str}"
                await dm.send(embed=embed)

        # Upvote image on Gelbooru
        elif payload.emoji.name == "upvote":
            if re.match(url, message.content[:33]):

                # Upvote
                requests.get(f"https://gelbooru.com/index.php?page=post&s=vote&id={image_id}&type=up", headers=head, cookies=cookies)

        elif payload.emoji.name == "remove_mes":

            if message.channel.category.name == cred[3]:
                await message.delete()
            else:
                await message.remove_reaction(payload.emoji, payload.member)

        # Remove unrecognised reactions
        else:
            await message.remove_reaction(payload.emoji, payload.member)

    # Privacy settings controls
    if message.channel.name == "privacy-settings":

        # Logic channels changing to private
        if payload.emoji.name == "private":

            # Set the #favourites channel to private
            if message.content == "#favourites":

                # Variables for code clarity
                category = get(client.guilds[0].categories, name=cred[3])
                channel = get(category.text_channels, name="favourites")

                # Remove the public reaction
                await message.remove_reaction(client.get_emoji(812358247641120778), payload.member)

                # Disallow registered users to view the channel
                await channel.edit(overwrites={get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=False), get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=False), payload.member: discord.PermissionOverwrite(read_messages=True)})

            # Set the #removed channel to private
            elif message.content == "#removed":

                # Variables for code clarity
                category = get(client.guilds[0].categories, name=cred[3])
                channel = get(category.text_channels, name="removed")

                # Remove the public reaction
                await message.remove_reaction(client.get_emoji(812358247641120778), payload.member)

                # Disallow registered users to view the channel
                await channel.edit(overwrites={get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=False), get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=False), payload.member: discord.PermissionOverwrite(read_messages=True)})

            # Set the #text channel to private
            elif message.content == "#text":

                # Variables for code clarity
                category = get(client.guilds[0].categories, name=cred[3])
                channel = get(category.text_channels, name="text")

                # Remove the public reaction
                await message.remove_reaction(client.get_emoji(812358247641120778), payload.member)

                # Disallow registered users to view the channel
                await channel.edit(overwrites={get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=False, send_messages=False), get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=False, send_messages=False), payload.member: discord.PermissionOverwrite(read_messages=True, send_messages=True)})

            elif message.content == "#custom1":
                try:
                    # Variables for code clarity
                    category = get(client.guilds[0].categories, name=cred[3])
                    channel = category.text_channels[3]

                    # Remove the public reaction
                    await message.remove_reaction(client.get_emoji(812358247641120778), payload.member)

                    # Disallow registered users to view the channel
                    await channel.edit(overwrites={
                        get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=False),
                        get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=False),
                        payload.member: discord.PermissionOverwrite(read_messages=True)})
                except IndexError:
                    await message.remove_reaction(client.get_emoji(812358391908532225), payload.member)

            elif message.content == "#custom2":
                try:
                    # Variables for code clarity
                    category = get(client.guilds[0].categories, name=cred[3])
                    channel = category.text_channels[4]

                    # Remove the public reaction
                    await message.remove_reaction(client.get_emoji(812358247641120778), payload.member)

                    # Disallow registered users to view the channel
                    await channel.edit(overwrites={
                        get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=False),
                        get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=False),
                        payload.member: discord.PermissionOverwrite(read_messages=True)})
                except IndexError:
                    await message.remove_reaction(client.get_emoji(812358391908532225), payload.member)

            elif message.content == "#custom3":
                try:
                    # Variables for code clarity
                    category = get(client.guilds[0].categories, name=cred[3])
                    channel = category.text_channels[5]

                    # Remove the public reaction
                    await message.remove_reaction(client.get_emoji(812358247641120778), payload.member)

                    # Disallow registered users to view the channel
                    await channel.edit(overwrites={
                        get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=False),
                        get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=False),
                        payload.member: discord.PermissionOverwrite(read_messages=True)})
                except IndexError:
                    await message.remove_reaction(client.get_emoji(812358391908532225), payload.member)

            # Remove reaction from unrecognised message
            else:
                await message.remove_reaction(payload.emoji, payload.member)

        # Logic channels changing to public
        elif payload.emoji.name == "public":

            # Set the #favourites channel to public
            if message.content == "#favourites":

                # Variables for code clarity
                category = get(client.guilds[0].categories, name=cred[3])
                channel = get(category.text_channels, name="favourites")

                # Remove the private reaction
                await message.remove_reaction(client.get_emoji(812358391908532225), payload.member)

                # Allow registered users to view the channel
                await channel.edit(overwrites={get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=True), get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=True)})

            # Set the #removed channel to public
            elif message.content == "#removed":

                # Variables for code clarity
                category = get(client.guilds[0].categories, name=cred[3])
                channel = get(category.text_channels, name="removed")

                # Remove the private reaction
                await message.remove_reaction(client.get_emoji(812358391908532225), payload.member)

                # Allow registered users to view the channel
                await channel.edit(overwrites={get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=True), get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=True)})

            # Ser the #text channel to public
            elif message.content == "#text":

                # Variables for code clarity
                category = get(client.guilds[0].categories, name=cred[3])
                channel = get(category.text_channels, name="text")

                # Remove the private reaction
                await message.remove_reaction(client.get_emoji(812358391908532225), payload.member)

                # Allow registered users to view the channel
                await channel.edit(overwrites={get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=True, send_messages=True), get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=True, send_messages=True)})

            elif message.content == "#custom1":
                try:
                    # Variables for code clarity
                    category = get(client.guilds[0].categories, name=cred[3])
                    channel = category.text_channels[3]
                    # Remove the public reaction
                    await message.remove_reaction(client.get_emoji(812358391908532225), payload.member)

                    # Disallow registered users to view the channel
                    await channel.edit(overwrites={
                        get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=True),
                        get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=True),
                        payload.member: discord.PermissionOverwrite(read_messages=True)})

                except IndexError:
                    await message.remove_reaction(client.get_emoji(812358247641120778), payload.member)

            elif message.content == "#custom2":
                try:
                    # Variables for code clarity
                    category = get(client.guilds[0].categories, name=cred[3])
                    channel = category.text_channels[4]
                    # Remove the public reaction
                    await message.remove_reaction(client.get_emoji(812358391908532225), payload.member)

                    # Disallow registered users to view the channel
                    await channel.edit(overwrites={
                        get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=True),
                        get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=True),
                        payload.member: discord.PermissionOverwrite(read_messages=True)})

                except IndexError:
                    await message.remove_reaction(client.get_emoji(812358247641120778), payload.member)

            elif message.content == "#custom3":
                try:
                    # Variables for code clarity
                    category = get(client.guilds[0].categories, name=cred[3])
                    channel = category.text_channels[5]
                    # Remove the public reaction
                    await message.remove_reaction(client.get_emoji(812358391908532225), payload.member)

                    # Disallow registered users to view the channel
                    await channel.edit(overwrites={
                        get(client.guilds[0].roles, name="Degenerate"): discord.PermissionOverwrite(read_messages=True),
                        get(client.guilds[0].roles, name="Guest"): discord.PermissionOverwrite(read_messages=True),
                        payload.member: discord.PermissionOverwrite(read_messages=True)})

                except IndexError:
                    await message.remove_reaction(client.get_emoji(812358247641120778), payload.member)

            # Remove reaction from unrecognised message
            else:
                await message.remove_reaction(payload.emoji, payload.member)

        # Remove unrecognised reactions
        else:
            await message.remove_reaction(payload.emoji, payload.member)


# Logic for controlling the messages
@client.event
async def on_message(message):

    # TODO DM commands
    if await check(message.channel):
        print("DM")
    else:
        # Remove every new message in the registration channel
        if message.channel.name == "registration":
            if not (message.author.name == "Gelbooru crawler"):
                await message.delete()

        if not message.channel.category.name == "settings and help":
            if message.content[0] == "[" and message.content[-1] == "]":
                await message.channel.purge(limit=1)
                id = message.content[1:-1]

                # Download user credentials from database
                cursor.execute(f"SELECT * FROM credentials WHERE discord_id ='{message.author.id}'")
                cred = cursor.fetchall()[0]

                # Create cookies
                cookies = {"user_id": cred[1], "pass_hash": cred[2]}

                # Parse the web page for the link of original resolution
                r = requests.get(f"https://gelbooru.com/index.php?page=post&s=view&id={id}", headers=head, cookies=cookies).text
                start = r.find("Fit Image to Window") + 50
                link = r[start:r[start:].find('"') + start]
                if link == "harset=":
                    link = "Image not Found"
                    mes = await message.channel.send(link)
                    rem_mes = await client.guilds[0].fetch_emoji(813446640320643092)
                    await mes.add_reaction(rem_mes)
                    return
                else:
                    # Add the image id to the database
                    cursor.execute(f"INSERT INTO images VALUES  ('{link}', '{id}');")
                    db.commit()
                mes = await message.channel.send(link)
                add_fav = await client.guilds[0].fetch_emoji(812687578205257768)
                upvote = await client.guilds[0].fetch_emoji(812673705536258068)
                img_det = await client.guilds[0].fetch_emoji(812738328205459486)
                await mes.add_reaction(add_fav)
                await mes.add_reaction(upvote)
                await mes.add_reaction(img_det)

    # Process the commands
    await client.process_commands(message)

# Remove x - 1 messages
@client.command()
@commands.has_any_role("Admin", "BOT") # Regulate the command usage
async def purge(ctx, limit):
    await ctx.channel.purge(limit=int(limit))


# Download new user's favourites and send them to the channel, takes credentials tuple from the database
async def download_favourites(user, limit=2147483647):

    # Variables for code clarity
    ids_list = []
    user_id = user[1]
    pass_hash = user[2]
    # user_category = discord.utils.get(client.guilds[0].categories, name=user_name)
    # channel = get(user_category.text_channels, name="favourites")

    # Fetched reactions
    add_fav = await client.guilds[0].fetch_emoji(812687578205257768)
    rem_fav = await client.guilds[0].fetch_emoji(812687316815839262)
    upvote = await client.guilds[0].fetch_emoji(812673705536258068)
    img_det = await client.guilds[0].fetch_emoji(812738328205459486)

    # Fetch images ids from the favourite page
    for n in range(0, limit, 50):

        # Load user credentials as cookies
        cookies = {"user_id": user_id, "pass_hash": pass_hash}

        # Request batches of 50 ids
        r = requests.get(f"https://gelbooru.com/index.php?page=favorites&s=view&id={user_id}&pid={n}", headers=head, cookies=cookies)

        # Parse the web page to get ids
        data = r.text[r.text.find("//<![CDATA["):].split("//<![CDATA[")[2:]
        ids = [id[id.find("[") + 1: id.find("]")] for id in data if (not id[id.find("[") + 1: id.find("]")] == "\n\t\t\tfilterPosts(posts)\n\t\t\t//")]

        # Stop if there is no new ids
        if len(ids) == 0:
            break

        # Add batches of 50 to the complete list
        ids_list.extend(ids)

    # Reverse the list to send the older images first
    ids_list.reverse()

    # Sent images
    n = 0

    # Get the original resolution of the image
    for id in ids_list:

        category = get(client.guilds[0].categories, name=user[3])
        channel = get(category.text_channels, name="favourites")

        error = False
        try:
            cursor.execute(f"SELECT `{channel.id}` FROM sent where '{channel.id}' IS NOT NULL;")
        except:
            error = True

        if error:
            sql = []
        else:
            sql = cursor.fetchall()

        # Check if the image wasn't send already
        if id not in [id[0] for id in sql]:

            # Count sent images
            n+=1

            # Load user credentials as cookies
            cookies = {"user_id": user_id, "pass_hash": pass_hash}

            # Parse the web page for the link of original resolution
            r = requests.get(f"https://gelbooru.com/index.php?page=post&s=view&id={id}", headers=head, cookies=cookies).text
            start = r.find("Fit Image to Window") + 50
            link = r[start:r[start:].find('"') + start]

            # Send image to the channel
            mes = await channel.send(link)
            await mes.add_reaction(add_fav)
            await mes.add_reaction(rem_fav)
            await mes.add_reaction(upvote)
            await mes.add_reaction(img_det)

            # Add the image id to the database
            cursor.execute(f"INSERT INTO images VALUES  ('{link}', '{id}');")

            # Add image to channel data
            try:
                cursor.execute(f"ALTER TABLE sent ADD `{mes.channel.id}` varchar(9);")
            except Exception:
                pass
            cursor.execute(f"INSERT INTO sent (`{mes.channel.id}`) VALUES ('{id}');")

            # Commit changes to the database every 50 images just to be sure
            if n % 50 == 0:
                db.commit()

            # DEBUG INFO
            print(id, user[3], "favourites")

    # Commit changes to the database
    db.commit()


# Command that is required from every user to store the credentials for later use
@client.command()
@commands.check(is_not_registered) # For now allow only new users to register the credentials
async def register(ctx, user_id, pass_hash):

    channels = client.guilds[0].text_channels

    # Direct message channel
    dm = await ctx.author.create_dm()

    if len(channels) > 450:
        await dm.send("Channel limit has been reached please contact KROKIk#0029, in the mean time you can still browse this server as guest.")
        return

    # Check if credentials are correct
    cookies = {"user_id": user_id, "pass_hash": pass_hash}
    r = requests.get(f"https://gelbooru.com/public/addfav.php?id=197798", headers=head, cookies=cookies).content
    if str(r, "utf-8") == "3":
        requests.get(f"https://gelbooru.com/index.php?page=favorites&s=delete&id=197798", headers=head, cookies=cookies)
    elif str(r, "utf-8") == "2":
        await dm.send("Something went wrong, make sure the credentials are correct")
        return

    # Variables for code clarity
    guild = client.guilds[0]
    degenerate = get(guild.roles, name="Degenerate")
    guest_role = get(guild.roles, name="Guest")
    owner = ctx.message.author
    guild = ctx.message.guild

    # Default #favourites permissions
    overwrites_fav = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        degenerate: discord.PermissionOverwrite(read_messages=True),
        guest_role: discord.PermissionOverwrite(read_messages=True),
        owner: discord.PermissionOverwrite(read_messages=True,)
    }

    # Default #removed permissions
    overwrites_removed = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        degenerate: discord.PermissionOverwrite(read_messages=False),
        guest_role: discord.PermissionOverwrite(read_messages=True),
        owner: discord.PermissionOverwrite(read_messages=True,)
    }

    # Default #text permissions
    overwrites_text = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        degenerate: discord.PermissionOverwrite(read_messages=False, send_messages=False),
        guest_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
        owner: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }

    # Parse the username from the profile page
    r = requests.get(f"https://gelbooru.com/index.php?page=account&s=profile&id={user_id}", headers=head).text
    name = r[r.find('<span class="profileUsernameDisplay">') + 37: r[r.find('<span class="profileUsernameDisplay">'):].find(" -") + r.find('<span class="profileUsernameDisplay">')].lower()

    # Add user credentials to teh database
    cursor.execute(f"INSERT INTO credentials VALUES  ('{ctx.author.id}', '{user_id}', '{pass_hash}', '{name}');")

    # Commit changes to the database
    db.commit()

    # Create category named after gelbooru username
    await guild.create_category(name=name)

    # Create channel within this category
    channel = await guild.create_text_channel(name="favourites", category=discord.utils.get(ctx.guild.categories, name=name), overwrites=overwrites_fav, nsfw=True)
    await channel.send(f"{name}:\nReact with <:rem_fav:812687316815839262> to remove image from this channel and move it to the #removed channel for confirmation\n\nEveryone else:\nReact with <:add_to_fav:812687578205257768> to add this image to your #favourites")

    # Create channel for removed favourites
    channel = await guild.create_text_channel(name="removed", category=discord.utils.get(ctx.guild.categories, name=name), overwrites=overwrites_removed, nsfw=True)
    await channel.send(f"{name}:\nReact with <:add_to_fav:812687578205257768> to cancel the image removal or with <:rem_fav:812687316815839262> to confirm image removal")

    # Create channel for chatting
    channel = await guild.create_text_channel(name="text", category=discord.utils.get(ctx.guild.categories, name=name), overwrites=overwrites_text, nsfw=True)
    await channel.send(f"Chat with others or use commands, list of commands available on #help")

    # Register user (give him the degenerate role)
    await ctx.message.author.add_roles(get(ctx.guild.roles, name="Degenerate"))

    # Remove guest role
    await ctx.message.author.remove_roles(get(ctx.guild.roles, name="Guest"))

    # Change nickname
    # Does not work with server owner
    try:
        await ctx.author.edit(nick=name)
    except:
        pass

    # If everything went as it should download the credentials tuple
    cursor.execute(f"SELECT * FROM credentials WHERE discord_id ='{ctx.author.id}'")
    cred = cursor.fetchall()[0]

    # Notify user
    await dm.send(f"Registration successful, you have been registered as {name}!")

    # Download favourites to the newly created channel
    await download_favourites(user=cred)


# View server as a guest
@client.command()
@commands.check(is_not_registered) # For now allow only new users to register the credentials
async def guest(ctx):
    await ctx.message.author.add_roles(get(ctx.guild.roles, name="Guest"))


# Add personal search channels
@client.command()
async def search(ctx, name, query):

    cursor.execute(f"SELECT * FROM credentials WHERE discord_id ='{ctx.author.id}'")
    cred = cursor.fetchall()[0]
    user_name = cred[3]

    # Variables for code clarity
    guild = client.guilds[0]
    degenerate = get(guild.roles, name="Degenerate")
    guest_role = get(guild.roles, name="Guest")
    owner = ctx.message.author

    if len(discord.utils.get(guild.categories, name=user_name).text_channels) >= 6:
        await ctx.channel.send("Custom channel limit has been reached!")
        return

    overwrites_fav = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        degenerate: discord.PermissionOverwrite(read_messages=True),
        guest_role: discord.PermissionOverwrite(read_messages=True),
        owner: discord.PermissionOverwrite(read_messages=True,)
    }

    # Create channel within this category
    channel = await guild.create_text_channel(name=name, category=discord.utils.get(guild.categories, name=user_name), overwrites=overwrites_fav, nsfw=True)

    await download_custom(user_name, name, query)

    # TODO Modify the message
    await channel.send(f"{user_name}:\nReact with <:rem_fav:812687316815839262> to remove image from this channel and move it to the #removed channel for confirmation\n\nEveryone else:\nReact with <:add_to_fav:812687578205257768> to add this image to your #favourites")

    # Insert channel into database AFTER it has been downloaded to prevent double downloading
    cursor.execute(f"INSERT INTO custom VALUES ('{user_name}', '{name}', '{query}')")
    db.commit()


async def download_custom(category_name, channel_name, query):

    add_fav = await client.guilds[0].fetch_emoji(812687578205257768)
    upvote = await client.guilds[0].fetch_emoji(812673705536258068)
    img_det = await client.guilds[0].fetch_emoji(812738328205459486)

    query_corrected = urllib.parse.quote(query.encode('utf-8'), safe='')

    channel = discord.utils.get(discord.utils.get(client.guilds[0].categories, name=category_name).text_channels, name=channel_name)

    error = False
    try:
        cursor.execute(f"SELECT `{channel.id}` FROM sent where '{channel.id}' IS NOT NULL;")
    except:
        error = True

    if error:
        sql = []
    else:
        sql = cursor.fetchall()

    # Check if the image wasn't send already

    url = f"https://gelbooru.com/index.php?page=post&s=list&tags={query_corrected}&pid=0"

    cookies = {"user_id": "735459", "pass_hash": "2fa49b950ca7f2fb2791b79f1a0cf8c73c2f36f1", "fringeBenefits": "yup"}

    r = requests.get(url, headers=head, cookies=cookies).text
    r = r[r.find("<div class=\"thumbnail-container\">") + 33:]
    r = r[:r.find("</script>")].split("</article>")
    ids = []
    for id in r:
        id = id[id.find("id=\"p") + 5:]
        id = id[:id.find("\" ")]
        ids.append(id)

    ids.reverse()
    for id in ids[1:]:

        if id not in [id[0] for id in sql]:
            # DEBUG info
            print(id, category_name, channel_name)

            r = requests.get(f"https://gelbooru.com/index.php?page=post&s=view&id={id}", headers=head, cookies=cookies).text
            start = r.find("Fit Image to Window") + 50
            link = r[start:r[start:].find('"') + start]

            # Send image to the channel
            mes = await channel.send(link)
            await mes.add_reaction(add_fav)
            await mes.add_reaction(upvote)
            await mes.add_reaction(img_det)

            # Add the image id to the database
            cursor.execute(f"INSERT INTO images VALUES  ('{link}', '{id}');")

            # Add image to channel data
            try:
                cursor.execute(f"ALTER TABLE sent ADD `{mes.channel.id}` varchar(9);")
            except:
                pass
            cursor.execute(f"INSERT INTO sent (`{mes.channel.id}`) VALUES ('{id}');")
    db.commit()


@client.command()
async def remove(ctx, name):
    # Get credentials
    cursor.execute(f"SELECT * FROM credentials WHERE discord_id ='{ctx.author.id}'")
    cred = cursor.fetchall()[0]

    # Remove from custom channel from database
    cursor.execute(f"DELETE FROM custom WHERE category ='{cred[3]}' AND channel ='{name}'")
    db.commit()

    # Delete channel from discord
    category = get(client.guilds[0].categories, name=cred[3])
    channel = get(category.text_channels, name=name)
    await channel.delete()


# Send message
@client.command()
@commands.has_any_role("Admin", "BOT") # Regulate the command usage
async def send(ctx, num):
    await purge(ctx, 1)

    # Fetched reactions
    public = await client.guilds[0].fetch_emoji(812358247641120778)
    private = await client.guilds[0].fetch_emoji(812358391908532225)

    if num == "registration":
        await ctx.channel.send("To register:\n• Log in into Gelbooru\n• Open developers tools (F12 on Chrome)\n• Open tab on the top called Application (if you cant see it press 2 arrows)\n• On the left extend Cookies and select https://gelbooru.com\n• From there copy the value of pass_hash and user_id\n• Paste them as command as follows:\n.register user_id pass_hash\n• Change the settings in the #privacy-settings channel\n\nTo view this server as guest type:\n .guest")
    elif num == "help":
        await ctx.channel.send("List of reactions with short explanation:\n<:add_to_fav:812687578205257768> - Add this image to favourites on Gelbooru\n<:rem_fav:812687316815839262> - Remove this image from favourites on Gelbooru\n<:public:812358247641120778> - Used in the privacy-settings channel to make a specific chanel(s) public for everyone to see\n<:private:812358391908532225> - Used in the privacy-settings channel to make a specific chanel(s) only available for you\n<:image_details:812738328205459486> - Receive image details via direct message\n<:upvote:812673705536258068> - upvote the image on gelbooru")
    elif num == "privacy":
        await ctx.channel.send("React with <:public:812358247641120778> to allow everyone to see this channel or react with <:private:812358391908532225> to make the channel only visible to you.\n")
        channel = await ctx.channel.send("#favourites")
        await channel.add_reaction(public)
        await channel.add_reaction(private)
        channel = await ctx.channel.send("#removed")
        await channel.add_reaction(public)
        await channel.add_reaction(private)
        c = await ctx.channel.send("#text")
        await c.add_reaction(public)
        await c.add_reaction(private)
        c = await ctx.channel.send("#custom1")
        await c.add_reaction(public)
        await c.add_reaction(private)
        c = await ctx.channel.send("#custom2")
        await c.add_reaction(public)
        await c.add_reaction(private)
        c = await ctx.channel.send("#custom3")
        await c.add_reaction(public)
        await c.add_reaction(private)


@client.group(invoke_without_command=True)
async def help(ctx):
    em = discord.Embed(title="List of commands", description="For detailed description of emotes please visit #help")
    em.add_field(name=".search", value="add custom search to your category (max 3), example usage: .search furry \"score:>20 furry bdsm\"")
    em.add_field(name=".remove", value="removes custom search, example usage: .remove furry")
    em.add_field(name=".unregister", value="(not implemented yet :p)removes your data from database and removes your access to the server, example usage: .unregister")
    em.add_field(name="custom images", value="you can also send any image to the text channel using its id in [], example usage: [12345]")
    await ctx.send(embed=em)


# Download all users new favourites every 1 hour and custom channels
@tasks.loop(minutes=5)
async def update():

    cursor.execute(f"SELECT * FROM credentials;")
    cred = cursor.fetchall()

    # TODO Clean up this code
    async def task(data):
        await download_favourites(user=data, limit=100)
        return data

    async def main():
        await asyncio.wait(
            [task(arg) for arg in cred]
        )

    await main()

    cursor.execute(f"SELECT * FROM custom;")
    cred = cursor.fetchall()

    async def task_t(data):
        category = data[0]
        channel = data[1]
        q = data[2]
        await download_custom(category, channel, q)
        return data

    async def main_t():
        await asyncio.wait(
            [task_t(arg) for arg in cred]
        )

    await main_t()


@tasks.loop(hours=8)
async def cleanup():

    # Get columns from database
    cursor.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'sent' ORDER BY ORDINAL_POSITION")
    columns = [column[0] for column in cursor.fetchall()]
    columns = columns[1:]

    for column in columns:

        # Get data from this column
        cursor.execute(f"SELECT `{column}` FROM sent")
        raw_data = cursor.fetchall()
        data = [x[0] for x in raw_data]

        while True:
            if len(data) == 0:
                break

            # Remove element if its not None
            if data[0] is not None:
                data = data[1:]
                continue

            else:
                # Remove all None values
                data2 = data
                try:
                    while True:
                        data2.remove(None)
                except ValueError:
                    pass

                # Move rest of ids to first open None values
                for element in data2:
                    cursor.execute(f"UPDATE sent SET `{column}` = NULL WHERE `{column}` = '{element}' LIMIT 1;")
                    cursor.execute(f"UPDATE sent SET `{column}` = '{element}' WHERE `{column}` IS NULL LIMIT 1;")
                    db.commit()

    # Delete empty rows from TABLE sent
    string = ''
    for column in columns:
        string += f"`{column}` IS NULL AND "
    cursor.execute(f"DELETE FROM sent WHERE {string[:-4]};")

    # COMMIT changed to database
    db.commit()


# Make sure bot is ready
@update.before_loop
@cleanup.before_loop
async def before():
    await client.wait_until_ready()


# TODO unregister command
# TODO prevent sql injection IMPORTANT

# Start jobs
update.start()
cleanup.start()

# Start the bot
client.run("")
