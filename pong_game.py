from typing import Callable, List, Optional
import pygame as pg

from assets.source.button import Button
from assets.source.switch_case import switch, case
from assets.images import sprite_sheet as sp_sh
import random as rd
import math as mh
import logging

pg.display.init()

logger = logging.getLogger(__name__)

handler = logging.StreamHandler()
logger.addHandler(handler)

handler = logging.FileHandler(filename="pong.long.log")
logger.addHandler(handler)

handler = logging.FileHandler(filename="pong.log", mode="w")
logger.addHandler(handler)


def multiply_vec(vec1: pg.Vector2, vec2: pg.Vector2):
    return pg.Vector2(vec1.x * vec2.x, vec1.y * vec2.y)


class App:
    all_keycodes = tuple(getattr(pg.constants, key_str) for key_str in
                         filter(lambda k: k.startswith("K_"), dir(pg.constants)))
    fps = 30

    def __init__(self):
        self.game = Game(self)
        self.menu = Menu(self)
        self.settings = Settings(self)
        self._scene: Scene = ...
        self.screen: pg.Surface = ...
        self.done = False
        self.clock = pg.time.Clock()
        self.scene = self.menu

    @property
    def scene(self):
        return self._scene

    @scene.setter
    def scene(self, value: "Scene"):
        self._scene = value
        self.update_screen()

    @property
    def scene_scale(self):
        return self.scene.settings["scale"][0] / self.scene.settings["size"][0], self.scene.settings["scale"][1] /\
               self.scene.settings["size"][1]

    def update_screen(self):
        pg.display.set_mode(self.scene.settings["scale"])
        pg.display.set_caption(self.scene.settings["title"])
        if self.scene.settings["icon"]:
            pg.display.set_icon(self.scene.settings["icon"])

        self.screen = pg.display.get_surface()

    def draw(self):
        self.screen.blit(pg.transform.scale(self.scene.draw(), self.scene.settings["scale"]), (0, 0))
        pg.display.update()

    def update(self):
        self.scene.update()

    def run(self):
        while not self.done:
            self.update()
            self.draw()
            self.handle_events()
            self.handle_input()
            self.clock.tick(self.fps)

    def handle_events(self):
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.done = True
                break
            if "events_filter" not in self.scene.settings or event.type in self.scene.settings["events_filter"]:
                self.scene.handle_event(event)

    def handle_input(self):
        keys_pressed = pg.key.get_pressed()
        for keycode in self.all_keycodes:
            if keys_pressed[keycode]:
                self.scene.handle_input(keycode)

    def get_mouse_pos(self):
        return pg.mouse.get_pos()[0] // self.scene_scale[0], pg.mouse.get_pos()[1] // self.scene_scale[1]


class Player(pg.sprite.Sprite):
    friction = 0.9
    up_force = pg.Vector2(y=-10)
    down_force = pg.Vector2(y=10)

    def __init__(self, pos: pg.Vector2, hit_box: pg.Rect, image: pg.Surface, walls: pg.Rect, control_delay: int):
        super().__init__()
        self.pos = pos
        self.vel = pg.Vector2()
        self._hit_box = hit_box
        self.hit_box_offset = pg.Vector2(hit_box.x, hit_box.y)
        self.image = image
        self.size = self.image.get_size()
        self.walls = walls
        self.control_delay = control_delay
        self.last_press = 0
        self.move_buffer = 0
        self.ball_bounce = pg.Vector2(-1, 1)

    @property
    def hit_box(self):
        return pg.Rect(*(self.pos + self.hit_box_offset), self._hit_box.w, self._hit_box.h)

    @property
    def rect(self):
        return pg.Rect(*self.pos, *self.size)

    def update(self, *args, **kwargs) -> None:
        self.pos += self.vel
        self.vel *= self.friction

        self.clamp_pos()

        if self.last_press > 0:
            self.last_press -= 1

    def up(self):
        self.vel += self.up_force

    def down(self):
        self.vel += self.down_force

    def control(self, mode: int):
        if self.last_press:
            self.move_buffer = mode
        else:
            if mode == 1:
                self.up()
                self.last_press += self.control_delay
                self.move_buffer = 0
            elif mode == 2:
                self.down()
                self.last_press += self.control_delay
                self.move_buffer = 0

    def clamp_pos(self):
        if self.hit_box.left < self.walls.left:
            self.pos.x = self.walls.left + 1
        if self.hit_box.right > self.walls.right:
            self.pos.x = self.walls.right - self.hit_box.w - 1
        if self.hit_box.top < self.walls.top:
            self.pos.y = self.walls.top + 1
        if self.hit_box.bottom > self.walls.bottom:
            self.pos.y = self.walls.bottom - self.hit_box.h - 1


class Ball(pg.sprite.Sprite):
    friction = 0.99
    horizontal = pg.Vector2(-1, 1)
    vertical = pg.Vector2(1, -1)

    def __init__(self, pos: pg.Vector2, vel: pg.Vector2, hit_box: pg.Rect, image: pg.Surface,
                 walls: pg.Rect,
                 bonce_interval: int):
        super().__init__()
        self.pos = pos
        self.vel = vel
        self._hit_box = hit_box
        self.hit_box_offset = pg.Vector2(hit_box.x, hit_box.y)
        self.image = image
        self.size = self.image.get_size()
        self.walls = walls
        self.bounce_interval = bonce_interval
        self.bounce_elapse = 0
        self.pads_bounce_interval = bonce_interval
        self.pads_bounce_elapse = 0

    @property
    def hit_box(self):
        return pg.Rect(*(self.pos + self.hit_box_offset), self._hit_box.w, self._hit_box.h)

    @property
    def rect(self):
        return pg.Rect(*self.pos, *self.size)

    def update(self, *args, **kwargs) -> None:
        self.pos += self.vel
        self.bounce()
        self.clamp_pos()

        if self.bounce_elapse > 0:
            self.bounce_elapse -= 1

        if self.pads_bounce_elapse > 0:
            self.pads_bounce_elapse -= 1

        if "pads" in kwargs:
            pads: pg.sprite.Group = kwargs["pads"]
            pad: Player
            for pad in pads:
                if self.hit_box.colliderect(pad.hit_box) and self.pads_bounce_elapse == 0:
                    si_x, si_y = multiply_vec(self.vel, pad.ball_bounce)
                    diff = pg.Vector2(self.hit_box.center) - pg.Vector2(pad.hit_box.center)
                    v_x, v_y = diff / diff.length() * 10
                    if v_x == 0:
                        v_x = 1
                    self.vel = pg.Vector2(mh.copysign(v_x, si_x), mh.copysign(v_y, si_y))
                    self.pads_bounce_elapse += self.pads_bounce_interval

        if "goals" in kwargs:
            goals: List[BallGoal] = kwargs["goals"]
            for goal in goals:
                goal.collide(self.hit_box)

    def bounce(self):
        if self.bounce_elapse > 0:
            return
        if self.hit_box.left < self.walls.left:
            self.vel = multiply_vec(self.vel, self.horizontal)
            self.pos += self.vel
            self.bounce_elapse += self.bounce_interval
        if self.hit_box.right > self.walls.right:
            self.vel = multiply_vec(self.vel, self.horizontal)
            self.pos += self.vel
            self.bounce_elapse += self.bounce_interval
        if self.hit_box.top < self.walls.top:
            self.vel = multiply_vec(self.vel, self.vertical)
            self.pos += self.vel
            self.bounce_elapse += self.bounce_interval
        if self.hit_box.bottom > self.walls.bottom:
            self.vel = multiply_vec(self.vel, self.vertical)
            self.pos += self.vel
            self.bounce_elapse += self.bounce_interval

    def clamp_pos(self):
        if self.hit_box.left < self.walls.left:
            self.pos.x = self.walls.left + 21
        if self.hit_box.right > self.walls.right:
            self.pos.x = self.walls.right + self.hit_box.w
        if self.hit_box.top < self.walls.top:
            self.pos.y = self.walls.top + self.vel.y
        if self.hit_box.bottom > self.walls.bottom:
            self.pos.y = self.walls.bottom + self.hit_box.h


class BallGoal:
    def __init__(self, rect: pg.Rect, on_collide: Callable):
        self.rect = rect
        self.on_collide = on_collide

    def collide(self, other: pg.Rect):
        if self.rect.colliderect(other):
            self.on_collide()


class Scene:
    app = None
    settings = {"size": (0, 0), "scale": (0, 0), "title": "", "icon": None}
    settings["icon"]: Optional[pg.Surface]

    def __init__(self, app):
        self.app = self.app or app

    def draw(self) -> pg.Surface:
        pass

    def update(self):
        pass

    def handle_input(self, k_id: int):
        pass

    def handle_event(self, event):
        pass


class Game(Scene):
    settings = {"size": (512, 256), "scale": (1024, 512), "title": "Pong", "icon": None}

    def __init__(self, app: App):
        super(Game, self).__init__(app)
        self.pl_img = pg.Surface((10, 50))
        self.pl_img.fill((255, 255, 255))
        self.bl_img = pg.Surface((10, 10))
        self.bl_img.fill((255, 255, 255))
        self.bounds = pg.Rect(20, 15, 482, 221)
        self.player = Player(pg.Vector2(30, 128), pg.Rect(0, 0, 10, 50), self.pl_img, self.bounds, 10)
        self.bot = Player(pg.Vector2(472, 128), pg.Rect(0, 0, 10, 50), self.pl_img, self.bounds, 10)
        self.ball: Ball = ...
        self.max_bounds = pg.Rect(self.bounds.x - 20, self.bounds.y - 20, self.bounds.width + 20,
                                  self.bounds.height + 20)
        self.players_group = pg.sprite.Group(self.player, self.bot)
        self.balls_group = pg.sprite.Group()
        self.left_goal = BallGoal(pg.Rect(20, 0, 10, 256), self.left_collide)
        self.right_goal = BallGoal(pg.Rect(492, 0, 10, 256), self.right_collide)
        self.goals = [self.left_goal, self.right_goal]
        self.player_score = 0
        self.bot_score = 0
        self.scoring_delay = 10
        self.scoring_elapse = 0
        self.respawn_ball()
        self.sheet = sp_sh.load_sprite_sheet("sprite_sheet.png", "sprite_sheet.json", 6)
        self.background = pg.Surface(self.settings["size"])
        self.background.fill((0, 0, 0))
        pg.draw.rect(self.background, (255, 255, 255), pg.Rect(10, 10, 10, self.settings["size"][1] - 20))
        pg.draw.rect(self.background, (255, 255, 255), pg.Rect(10, 10, self.settings["size"][0] - 20, 10))
        pg.draw.rect(self.background, (255, 255, 255), pg.Rect(self.settings["size"][0] - 20, 10, 10,
                                                               self.settings["size"][1] - 20))
        pg.draw.rect(self.background, (255, 255, 255), pg.Rect(10, self.settings["size"][1] - 20,
                                                               self.settings["size"][0] - 20, 10))

        pg.draw.rect(self.background, (255, 255, 255), pg.Rect(self.settings["size"][0]//2 - 5, 10, 10,
                                                               self.settings["size"][1] - 20))

    def draw(self):
        screen = pg.Surface(self.settings["size"])
        screen.blit(self.background, (0, 0))
        self.players_group.draw(screen)
        self.balls_group.draw(screen)
        self.draw_text(screen)
        return screen

    def draw_text(self, surface: pg.Surface):
        if not self.sheet.generated:
            self.sheet.generate()
        pl_score_len = len(str(self.player_score)) * self.sheet.scale * 4
        # noinspection PyUnusedLocal
        bot_score_len = len(str(self.bot_score)) * self.sheet.scale * 4
        start_x = 256 - pl_score_len - 30
        for letter in str(self.player_score):
            surface.blit(self.sheet.get(letter), (start_x, 30))
            start_x += self.sheet.scale * 5

        start_x = 256 + 30
        for letter in str(self.bot_score):
            surface.blit(self.sheet.get(letter), (start_x, 30))
            start_x += self.sheet.scale * 5

    def respawn_ball(self):
        if isinstance(self.ball, Ball):
            self.ball.kill()

        ball_vec = pg.Vector2(rd.random() * 20 - 10, rd.random() * 20 - 10)
        ball_vec_l = ball_vec.length()
        if ball_vec_l and ball_vec.x:
            ball_vec = ball_vec / ball_vec_l * 10
        else:
            ball_vec = pg.Vector2(8, 9)

        self.ball = Ball(pg.Vector2(256, 128), ball_vec, pg.Rect(0, 0, 10, 10), self.bl_img, self.bounds,
                         10)
        self.ball.add(self.balls_group)

    def update(self):
        if not self.max_bounds.contains(self.ball.hit_box):
            self.respawn_ball()
        self.players_group.update()
        self.balls_group.update(pads=self.players_group, goals=self.goals)

        # bot control
        if self.bot.hit_box.centery > self.ball.hit_box.centery:
            self.bot.control(1)
        if self.bot.hit_box.centery < self.ball.hit_box.centery:
            self.bot.control(2)

        if self.scoring_elapse > 0:
            self.scoring_elapse -= 1

    def handle_input(self, k_id: int):
        with switch(k_id):
            # noinspection PyCallingNonCallable
            if case(pg.K_w):
                self.player.control(1)
            # noinspection PyCallingNonCallable
            if case(pg.K_s):
                self.player.control(2)

    def left_collide(self):
        if self.scoring_elapse:
            return
        self.bot_score += 1
        self.scoring_elapse += self.scoring_delay

    def right_collide(self):
        if self.scoring_elapse:
            return
        self.player_score += 1
        self.scoring_elapse += self.scoring_delay


class Menu(Scene):
    settings = {"size": (512, 256), "scale": (1024, 512), "title": "Pong Menu", "icon": None,
                "events_filter": {pg.MOUSEBUTTONDOWN}}

    def __init__(self, app):
        super(Menu, self).__init__(app)

        def click():
            self.app.scene = self.app.game

        self.screen = pg.Surface(self.settings["size"])

    def draw(self) -> pg.Surface:
        self.screen.fill((0, 0, 0))
        return self.screen

    def handle_event(self, event):
        pass


class Settings(Scene):
    pass
