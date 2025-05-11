"""
war card game client and server
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import socket
import socketserver
import threading
import sys


"""
Namedtuples work like classes, but are much more lightweight so they end
up being faster. It would be a good idea to keep objects in each of these
for each game which contain the game's state, for instance things like the
socket, the cards given, the cards still available, etc.
"""
Game = namedtuple("Game", ["p1", "p2"])

# Stores the clients waiting to get connected to other clients
waiting_clients = []


class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3


class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2

def readexactly(sock, numbytes):
    """
    Accumulate exactly `numbytes` from `sock` and return those. If EOF is found
    before numbytes have been received, be sure to account for that here or in
    the caller.
    """
    acc = b""
    while len(acc) < numbytes:
        chunk = sock.recv(numbytes - len(acc))
        if not chunk:
            raise ConnectionError("error with connecting to socket")
        acc += chunk
    return acc


def kill_game(game):
    """
    TODO: If either client sends a bad message, immediately nuke the game.
    """
    try:
        logging.debug("kill game - close p1")
        game.p1.close()
    except Exception as e:
        logging.error(f"cannot close p1: {e}")
    try:
        logging.debug("kill game - close p2")
        game.p2.close()
    except Exception as e:
        logging.error(f"cannot close p2 socket: {e}")


def compare_cards(card1, card2):
    """
    TODO: Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    card1 = card1%13
    card2= card2%13

    if card1<card2:
        return -1
    elif card1 == card2:
        return 0
    else:
        return 1
    

def deal_cards():
    """
    TODO: Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """
    allcards = list(range(52))
    random.shuffle(allcards)
    hand1 = allcards[0:26]
    hand2 = allcards[26:]
    return hand1, hand2
    

def serve_game(host, port):
    """
    TODO: Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
    sock.bind((host, port))
    sock.listen()
    logging.info(f"Server listening on {host}: {port}")

    while True:
        connection, address = sock.accept()
        logging.debug(f"connection accepted from {address}")
        waiting_clients.append(connection)

        if len(waiting_clients) >= 2:
            p1 = waiting_clients.pop(0)
            p2 = waiting_clients.pop(0)
            game = Game(p1,p2)
            #game
            p1_sock = game.p1
            p2_sock = game.p2 

            try:
                req_p1 = readexactly(p1_sock,2)
                req_p2 = readexactly(p2_sock,2)
                #if neither want game, end game
                if req_p1[0] != Command.WANTGAME.value or req_p2[0] != Command.WANTGAME.value:
                    kill_game(game)
                    return
                cards_p1, cards_p2 = deal_cards()
                p1_sock.sendall(bytes([Command.GAMESTART.value]) + bytes(cards_p1))
                p2_sock.sendall(bytes([Command.GAMESTART.value]) + bytes(cards_p2))
                score_p1 = 0
                score_p2 = 0
                used_p1 = set()
                used_p2 = set()

                for _ in range(26):
                    recv_p1 = readexactly(p1_sock, 2)
                    recv_p2 = readexactly(p2_sock,2)
                    if recv_p1[0] != Command.PLAYCARD.value or recv_p2[0] != Command.PLAYCARD.value :
                        kill_game(game)
                        return
                    if recv_p1[1] in used_p1 or recv_p1[1] not in cards_p1 or recv_p2[1] in used_p2 or recv_p2[1] not in cards_p2:
                        kill_game(game) #make sure the req sent is a valid card 
                        return
                    
                    used_p1.add(recv_p1[1])
                    used_p2.add(recv_p2[1])

                    compare = compare_cards(recv_p1[1], recv_p2[1])
                    if compare == 1:
                        score_p1 += 1
                        result_p1 = Result.WIN.value
                        result_p2 = Result.LOSE.value
                    elif compare == 0: #tie
                        result_p1 = Result.DRAW.value
                        result_p2 = Result.DRAW.value
                    elif compare == -1:
                        score_p2 += 1
                        result_p2 = Result.WIN.value
                        result_p1 = Result.LOSE.value
                    p1_sock.sendall(bytes([Command.PLAYRESULT.value, result_p1]))
                    p2_sock.sendall(bytes([Command.PLAYRESULT.value, result_p2]))
            except Exception as e:
                logging.error(f"Error:{e}")
                kill_game(game)
            try:
                p1_sock.close()
                p2_sock.close()
            except:
                logging.error(f"Error could not close sockets:{e}")

    

async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)

async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port)
        # send want game
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0

def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        
        asyncio.set_event_loop(loop)
        
    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]
        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients
        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()

if __name__ == "__main__":
    # Changing logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1:])
