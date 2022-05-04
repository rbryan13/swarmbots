#!/usr/bin/env python3

import argparse
import asyncio
import math
import pygame   # type: ignore
import random
import time
from typing import Tuple

import cProfile
import pstats


XY = Tuple[float, float]
COLOR = Tuple[int, int, int]

class Arena():
    """The arena containing the robot swarm"""

    def __init__(self, numberOfRobots: int):
        self.initForPygame()
        self.initForSwarm(numberOfRobots)

    def initForPygame(self):
        pygame.init()
        self.keepRunning = True
        self.width = 1000
        self.height = 750
        self.surface = pygame.display.set_mode((self.width, self.height))
        self.drawInterval = 1.0 / 15

    def initForSwarm(self, numberOfRobots: int):
        def randomBot():
            # random position and color
            x = random.randrange(0, self.width)
            y = random.randrange(0, self.height)
            r = random.randrange(0, 255)
            g = random.randrange(0, 255)
            b = random.randrange(0, 255)
            # random length for its async nap
            napMsec = random.randrange(20, 200)
            nap = napMsec / 1000.0
            robot = Robot(self, (x, y), (r, g, b), nap)
            return robot

        self.robots = [randomBot() for _ in range(numberOfRobots)]
        self.centroid = self.refreshCentroid()

    def runSync(self, stopAfterNFrames=0):
        """Synchronous simulation: loop drawing all bots then updating them"""
        nFrames = 0
        while True:
            now = time.perf_counter()
            next = now + self.drawInterval

            self.handlePygameEvents()
            if not self.keepRunning:
                break

            self.drawBots()
            nFrames += 1
            if stopAfterNFrames and nFrames >= stopAfterNFrames:
                break

            for robot in self.robots:
                robot.update()
            self.refreshCentroid()

            if next > now:
                time.sleep(next - now)

    async def runAsync(self, stopAfterNFrames=0):
        """Async simulation: start bot tasks and gui task,
        then wait for them all to finish"""
        botTasks = [robot.runAsync() for robot in self.robots]
        guiTask = self.runGuiAsync(stopAfterNFrames)
        await asyncio.gather(guiTask, *botTasks)

    async def runGuiAsync(self, stopAfterNFrames):
        """Periodically update the screen"""
        nFrames = 0
        while True:
            self.handlePygameEvents()
            if self.keepRunning:
                self.drawBots()
                nFrames += 1
                if stopAfterNFrames and nFrames >= stopAfterNFrames:
                    self.keepRunning = False
                    break
                await asyncio.sleep(self.drawInterval)
            else:
                break

    def handlePygameEvents(self):
        """Drain and handle any pending pygame events.
        Returns when no more are pending, without waiting
        for more to come in. This lets it cooperate
        with another event loop, for instance asyncio.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.display.quit()
                self.keepRunning = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    quit = pygame.event.Event(pygame.QUIT)
                    pygame.event.post(quit)

    def drawBots(self):
        """draw all the robots and update the screen to suit"""
        # draw the arena background
        self.surface.fill((0, 0, 0))
        # draw the robots
        for robot in self.robots:
            robot.draw(self.surface)
        # tell pygame to put robots on the screen
        pygame.display.flip()

    def findCentroid(self) -> XY:
        """returns themost recently computed centroid"""
        # This relies on refreshCentroid() being called
        # whenever robots move, probably once per frame.
        # That leaves slightly stale data in the async case.
        return self.centroid

    def refreshCentroid(self):
        """Compute and save the centroid (mean position)
        of the swarm"""
        sumx, sumy = 0, 0
        for bot in self.robots:
            x, y = bot.xy
            sumx += x
            sumy += y
        nbots = len(self.robots)
        self.centroid = sumx / nbots, sumy / nbots
        return self.centroid


class Robot():

    def __init__(self, arena: Arena, xy: XY, color: COLOR, nap: float):
        self.arena = arena
        self.xy = xy
        self.color = color
        self.nap = nap
        self.prevTime = time.perf_counter()
        # robots all travel the same speed, in whatever direction
        self.pixPerSecond = 50

    async def runAsync(self):
        """loop doing update then nap, asynchronously"""
        while self.arena.keepRunning:
            self.update()
            await asyncio.sleep(self.nap)

    def update(self) -> None:
        """
        Dumb swarming: move in the direction of overall centroid.
        Note: for large numbers of robots, this will probably not
        converge to a single point. Infrequently updated bots
        will overshoot the actual centroid every time.
        """
        now = time.perf_counter()
        # how long has it been since previous update
        dt = now - self.prevTime
        # where we are now
        x, y = self.xy
        # where to move toward
        cx, cy = self.arena.findCentroid()
        # direction to centroid
        # we could use atan2 then sin and cos
        distx, disty = cx - x, cy - y
        dist = max(1, math.hypot(distx, disty))
        dirx, diry = distx / dist, disty / dist
        # scalar and vector distance traveled since last update
        travel = self.pixPerSecond * dt
        dx, dy = travel * dirx, travel * diry
        # increment position
        self.xy = x + dx, y + dy
        # save current timestamp for next update
        self.prevTime = now

    def draw(self, surface):
        """robot draws itself on the surface"""
        # With less dumb swarming, maybe interesting to draw a line
        # from where it was last time to where it is now.
        x, y = self.xy
        pygame.draw.rect(surface, self.color, pygame.Rect(x, y, 1, 1))


# ****************************************

def simulate(numberOfRobots, useAsync, measureProfile, stopAfterNFrames):
    """Run the simulation"""

    info = f"Simulate {numberOfRobots} bots, {'async' if useAsync else 'sync'}"
    if stopAfterNFrames:
        info += f", stop after {stopAfterNFrames} frames"
    print(info)

    arena = Arena(numberOfRobots)

    def asyncDoit():
        asyncio.run(arena.runAsync(stopAfterNFrames))

    def syncDoit():
        arena.runSync(stopAfterNFrames)

    doit = asyncDoit if useAsync else syncDoit

    if not measureProfile:
        doit()
    else:
        # cProfile insists on a string, not a callable.
        global doprof
        doprof = doit
        cProfile.runctx("doprof()",
            globals=globals(), locals={},
            filename="profile.dat")
        p = pstats.Stats("profile.dat")
        p.sort_stats(pstats.SortKey.TIME)   # CUMULATIVE
        p.print_stats(30)


# ****************************************

if __name__ == "__main__":
    # Oh heck, while I'm overengineering...
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default="20000", dest="numberOfRobots",
        help="number of robots, default 20_000")
    parser.add_argument("-s", action="store_true", dest="useSync",
        help="use sync instead of async")
    parser.add_argument("-p", action="store_true", dest="measureProfile",
        help="measure performance profile")
    args = parser.parse_args()
    numberOfRobots = int(args.numberOfRobots)
    useAsync = not args.useSync
    measureProfile = args.measureProfile

    nFrames = 10 if useAsync else 100
    stopAfterNFrames = nFrames if measureProfile else 0
    simulate(numberOfRobots, useAsync, measureProfile, stopAfterNFrames)
