import logging
import math as mh
import random as rd
import webbrowser as wb
from typing import Callable, List, Optional, Tuple, Union

import pygame as pg

from assets.images import sprite_sheet as sp_sh
from assets.sounds import sounds
from assets.source.switch_case import switch, case

from client import Client

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
        self.client = Client()
        self.game = Game(self)
        self.menu = Menu(self)
        self.tutorial = Tutorial(self)
        self._scene: Scene = ...
        self.screen: pg.Surface = ...
        self.done = True
        self.clock = pg.time.Clock()
        self.scene = self.menu
        self.bgm = sounds.get_song("pong_bgm.wav")

    @property
    def scene(self) -> "Scene":
        return self._scene

    @scene.setter
    def scene(self, value: "Scene"):
        self._scene = value
        if not self.done:
            self._scene.initialize()
        self.update_screen()

    @property
    def scene_scale(self):
        return self.scene.settings["scale"][0] / self.scene.settings["size"][0], self.scene.settings["scale"][1] / \
               self.scene.settings["size"][1]

    def update_screen(self):
        pg.display.set_mode(self.scene.settings["scale"])
        pg.display.set_caption(self.scene.settings["title"])
        if self.scene.settings["icon"]:
            pg.display.set_icon(self.scene.settings["icon"])

        self.screen = pg.display.get_surface()

    def get_scene_screen(self):
        return pg.Surface(self.scene.settings["size"])

    def draw(self):
        self.screen.blit(pg.transform.scale(self.scene.draw(), self.scene.settings["scale"]), (0, 0))
        pg.display.update()

    def update(self):
        self.scene.update()

    def run(self):
        self.bgm.play(-1)
        self.done = False
        self._scene.initialize()
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
        self.handle_mouse_press()
        keys_pressed = pg.key.get_pressed()
        for keycode in self.all_keycodes:
            if keys_pressed[keycode]:
                self.scene.handle_input(keycode)

    def handle_mouse_press(self):
        pressed = pg.mouse.get_pressed(3)
        mouse_pos = self.get_mouse_pos()
        for key in range(3):
            if pressed[key]:
                self.scene.handle_mouse_press(key, (int(mouse_pos[0]), int(mouse_pos[1])))

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
                 walls: pg.Rect, bounce_interval: int, pads_bounce_interval: int):
        super().__init__()
        self.pos = pos
        self.vel = vel
        self._hit_box = hit_box
        self.hit_box_offset = pg.Vector2(hit_box.x, hit_box.y)
        self.image = image
        self.size = self.image.get_size()
        self.walls = walls
        self.bounce_interval = bounce_interval
        self.bounce_elapse = 0
        self.pads_bounce_interval = pads_bounce_interval
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
                    if diff.length():
                        v_x, v_y = diff / diff.length() * 10
                    else:
                        v_x, v_y = 8, 6
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
    settings = {"size": (0, 0), "scale": (0, 0), "title": "", "icon": ...}
    settings["icon"]: Optional[pg.Surface]

    def __init__(self, app):
        self.app = self.app or app
        self.initialized = False
        self.font: sp_sh.SpriteSheet = ...

    def draw(self) -> pg.Surface:
        pass

    def update(self):
        pass

    def handle_input(self, k_id: int):
        pass

    def handle_mouse_press(self, key: int, pos: Tuple[int, int]):
        pass

    def handle_event(self, event):
        pass

    def init(self):
        if not self.initialized:
            self.initialize()
            self.initialized = True

    def initialize(self):
        pass

    def render_text(self, surface: pg.Surface, text: Union[List[str], str], pos: Tuple[int, int], right_offset: int,
                    down_offset: int, font: Optional[sp_sh.SpriteSheet] = None, calculate_offset: bool = False,
                    space_offset: int = 0, enter_offset: int = 0):
        text += "\n"
        font = font or self.font
        cur_pos = pos
        last_letter: Optional[pg.Surface] = None
        biggest_width = 0
        for letter in text:
            if letter == "\n":
                if biggest_width < cur_pos[0]:
                    biggest_width = cur_pos[0]
                if calculate_offset:
                    cur_pos = pos[0], cur_pos[1] + (enter_offset if not last_letter else last_letter.get_height()) \
                              + down_offset
                else:
                    cur_pos = pos[0], cur_pos[1] + down_offset

            elif letter == " ":
                if calculate_offset:
                    cur_pos = cur_pos[0] + (space_offset if not last_letter else last_letter.get_width()), cur_pos[1]
                else:
                    cur_pos = cur_pos[0] + right_offset, cur_pos[1]
            else:
                last_letter = font.get(letter)
                surface.blit(last_letter, cur_pos)
                if calculate_offset:
                    cur_pos = cur_pos[0] + last_letter.get_width() + right_offset, cur_pos[1]
                else:
                    cur_pos = cur_pos[0] + right_offset, cur_pos[1]
        width = biggest_width - pos[0]
        height = cur_pos[1] - pos[1]
        return pg.Rect(pos, (width, height))


class Game(Scene):
    settings = {"size": (512, 256), "scale": (1024, 512), "title": "Pong Game", "icon": None,
                "events_filter": {pg.MOUSEBUTTONDOWN, pg.KEYDOWN, pg.KEYUP}}

    def __init__(self, app: App):
        super(Game, self).__init__(app)
        self.pl_img = pg.Surface((10, 50), pg.SRCALPHA)
        self.pl_img.fill((255, 255, 255))

        self.pl_disabled_img = pg.Surface((10, 50), pg.SRCALPHA)
        self.pl_disabled_img.fill((255, 255, 255, 100))

        self.bl_img = pg.Surface((10, 10), pg.SRCALPHA)
        pg.draw.circle(self.bl_img, (255, 255, 255), (5, 5), 5)
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
        self.sheet = sp_sh.load_sprite_sheet("alphabet.png", "sprite_sheet.json", "box", 6)
        self.background = pg.Surface(self.settings["size"])
        self.background.fill((0, 0, 0))
        self.screen: pg.Surface = ...
        pg.draw.rect(self.background, (255, 255, 255), pg.Rect(10, 10, 10, self.settings["size"][1] - 20))
        pg.draw.rect(self.background, (255, 255, 255), pg.Rect(10, 10, self.settings["size"][0] - 20, 10))
        pg.draw.rect(self.background, (255, 255, 255), pg.Rect(self.settings["size"][0] - 20, 10, 10,
                                                               self.settings["size"][1] - 20))
        pg.draw.rect(self.background, (255, 255, 255), pg.Rect(10, self.settings["size"][1] - 20,
                                                               self.settings["size"][0] - 20, 10))

        pg.draw.rect(self.background, (255, 255, 255), pg.Rect(self.settings["size"][0] // 2 - 5, 10, 10,
                                                               self.settings["size"][1] - 20))

        self.pl_score_rect = pg.Rect(256, 30, 0, 0)
        self.bt_score_rect = pg.Rect(256, 30, 0, 0)

        self.left_side = pg.Rect(20, 20, self.settings["size"][0] // 2 - 25, self.settings["size"][1] - 40)
        self.right_side = pg.Rect(self.settings["size"][0] // 2 + 5, 20, self.settings["size"][0] // 2 - 25,
                                  self.settings["size"][1] - 40)

        self.title = "pong"

    def draw(self):
        self.screen.fill((0, 0, 0))
        self.screen.blit(self.background, (0, 0))
        self.players_group.draw(self.screen)
        self.balls_group.draw(self.screen)
        self.draw_text(self.screen)
        return self.screen

    def initialize(self):
        self.sheet.generate()
        self.screen = self.app.get_scene_screen()
        self.settings["icon"] = self.sheet.get("logo")
        self.app.update_screen()

        self.generate_score_pos()

    def generate_score_pos(self, reset_pos: Optional[Tuple[int, int]] = None,
                           reset_pos2: Optional[Tuple[int, int]] = None, back: bool = True):
        reset_pos = reset_pos if reset_pos else (256, 30) if back else self.pl_score_rect.topleft
        reset_pos2 = reset_pos2 if reset_pos2 else (256, 30) if back else self.bt_score_rect.topleft

        self.pl_score_rect.topleft = reset_pos
        self.pl_score_rect = self.render_text(self.screen, str(self.player_score), self.pl_score_rect.topleft, 8, 0,
                                              self.sheet, True)

        if back:
            # noinspection SpellCheckingInspection
            self.pl_score_rect.topleft = (self.pl_score_rect.x - self.pl_score_rect.w - 30, self.pl_score_rect.y)

        self.bt_score_rect.topleft = reset_pos2
        self.bt_score_rect = self.render_text(self.screen, str(self.player_score), self.bt_score_rect.topleft, 8, 0,
                                              self.sheet, True)

        if back:
            # noinspection SpellCheckingInspection
            self.bt_score_rect.topleft = (self.bt_score_rect.x + 38, self.bt_score_rect.y)

    def draw_text(self, surface: pg.Surface):
        self.render_text(surface, str(self.player_score), self.pl_score_rect.topleft, 8, 0,
                         self.sheet, True)

        self.render_text(surface, str(self.bot_score), self.bt_score_rect.topleft, 8, 0,
                         self.sheet, True)
        return

        # pl_score_len = len(str(self.player_score)) * self.sheet.scale * 4
        # # noinspection PyUnusedLocal
        # bot_score_len = len(str(self.bot_score)) * self.sheet.scale * 4
        # start_x = 256 - pl_score_len - 30
        # for letter in str(self.player_score):
        #     surface.blit(self.sheet.get(letter), (start_x, 30))
        #     start_x += self.sheet.scale * 5
        #
        # start_x = 256 + 30
        # for letter in str(self.bot_score):
        #     surface.blit(self.sheet.get(letter), (start_x, 30))
        #     start_x += self.sheet.scale * 5

    def respawn_ball(self):
        if isinstance(self.ball, Ball):
            self.ball.kill()

        ball_vec = pg.Vector2(rd.random() * 20 - 10, rd.random() * 20 - 10)
        ball_vec_l = ball_vec.length()
        if ball_vec_l and ball_vec.x:
            ball_vec = ball_vec / ball_vec_l * 10
        else:
            ball_vec = pg.Vector2(8, 9)

        self.ball = Ball(pg.Vector2(256, 128), ball_vec, pg.Rect(0, 0, 10, 10), self.bl_img, self.bounds, 0, 5)
        self.ball.add(self.balls_group)

    def update(self):
        if not self.max_bounds.contains(self.ball.hit_box):
            self.respawn_ball()
        self.players_group.update()
        self.balls_group.update(pads=self.players_group, goals=self.goals)

        # bot control
        self.control_bot()

        if self.scoring_elapse > 0:
            self.scoring_elapse -= 1

        if self.left_side.contains(self.bt_score_rect) and self.right_side.contains(self.pl_score_rect):
            raise RuntimeError("Do not fake your score!")

    def control_bot(self):
        if self.bot.hit_box.centery > self.ball.hit_box.centery:
            self.bot.control(1)
        if self.bot.hit_box.centery < self.ball.hit_box.centery:
            self.bot.control(2)

    def handle_input(self, k_id: int):
        with switch(k_id):
            # noinspection PyCallingNonCallable
            if case(pg.K_w):
                self.player.control(1)
            # noinspection PyCallingNonCallable
            if case(pg.K_s):
                self.player.control(2)

    def handle_mouse_press(self, key: int, pos: Tuple[int, int]):
        if key == 0:
            if self.pl_score_rect.collidepoint(pos):
                # noinspection PyTypeChecker
                fix_pos: Tuple[int, int] = (*(pg.Vector2(pos) - pg.Vector2(self.pl_score_rect.center) +
                                              pg.Vector2(self.pl_score_rect.topleft)),)
                self.generate_score_pos(fix_pos, back=False)
            if self.bt_score_rect.collidepoint(pos):
                # noinspection PyTypeChecker
                fix_pos: Tuple[int, int] = (*(pg.Vector2(pos) - pg.Vector2(self.bt_score_rect.center) +
                                              pg.Vector2(self.bt_score_rect.topleft)),)
                self.generate_score_pos(reset_pos2=fix_pos, back=False)

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
                "events_filter": {pg.MOUSEBUTTONDOWN, pg.KEYDOWN, pg.KEYUP}}

    def __init__(self, app):
        super(Menu, self).__init__(app)
        self.screen: pg.Surface = ...
        self.font = sp_sh.load_sprite_sheet("alphabet.png", "sprite_sheet.json", "box", 8)
        self.small_font = sp_sh.load_sprite_sheet("alphabet.png", "sprite_sheet.json", "box", 4)
        self.really_small_font = sp_sh.load_sprite_sheet("alphabet.png", "sprite_sheet.json", "box", 2)
        self.title_rect: pg.Rect = pg.Rect(0, 0, 0, 0)
        self.play_rect: pg.Rect = pg.Rect(0, 0, 0, 0)
        self.tutorial_rect: pg.Rect = pg.Rect(0, 0, 0, 0)
        self.quit_rect: pg.Rect = pg.Rect(0, 0, 0, 0)
        self.pygame_rect: pg.Rect = pg.Rect(0, 0, 0, 0)
        self.option_selected: int = ...
        self.title = "pong"
        self.description_open: bool = False
        self.epilepsy_warning = False

    def initialize(self):
        self.font.generate()
        self.small_font.generate()
        self.screen = self.app.get_scene_screen()
        self.settings["icon"] = self.font.get("logo")
        self.app.update_screen()

    def draw(self) -> pg.Surface:
        self.screen.fill((0, 0, 0))
        if self.description_open:
            if self.epilepsy_warning:
                self.screen.fill((rd.randint(0, 255), rd.randint(0, 255), rd.randint(0, 255)))
            text = "welcome to pong, the game where you need\nto bounce ball and gain score.\n" \
                   "\nrequirements:\n" \
                   "- python 3.8 or higher\n" \
                   "- pygame\n" \
                   "\ndescription:\n" \
                   "this game was made by me and 'mio coder'\nfor summer 2021 pygame game jam\n" \
                   "theme was: remake old game with a twist\n" \
                   "twist for this game:" \
                   "it is possible that we hid\nsome 'secrets'\n" \
                   "to this game"
            self.render_text(self.screen, text, (0, 0), 6, 2, self.really_small_font, True, 40)
        else:
            if self.epilepsy_warning:
                self.screen.fill((rd.randint(0, 255), rd.randint(0, 255), rd.randint(0, 255)))
            self.title_rect = self.render_text(self.screen, self.title, (0, 0), 8, 0, self.font, True, 40)
            self.play_rect = self.render_text(self.screen, "play", (0, 75), 8, 0, self.small_font, True, 40)
            self.tutorial_rect = self.render_text(self.screen, "tutorial", (0, 125), 8, 0, self.small_font, True, 40)
            self.quit_rect = self.render_text(self.screen, "quit", (0, 175), 8, 0, self.small_font, True, 40)

            self.pygame_rect = self.render_text(self.screen, [*list("made with "), ":pygame:", *list("pygame")],
                                                (325, 225), 2, 0, self.really_small_font, True, 40)

            if not isinstance(self.option_selected, int):
                pass
            elif self.option_selected == 0:
                pg.draw.rect(self.screen, (255, 255, 255), self.play_rect, 5)
            elif self.option_selected == 1:
                pg.draw.rect(self.screen, (255, 255, 255), self.tutorial_rect, 5)
            elif self.option_selected == 2:
                pg.draw.rect(self.screen, (255, 255, 255), self.quit_rect, 5)
            else:
                self.option_selected %= 3

        return self.screen

    def update(self):
        mouse_pos = self.app.get_mouse_pos()
        if self.play_rect.collidepoint(mouse_pos):
            self.option_selected = 0
        elif self.tutorial_rect.collidepoint(mouse_pos):
            self.option_selected = 1
        elif self.quit_rect.collidepoint(mouse_pos):
            self.option_selected = 2

    def pong_title_easter_egg(self):
        if rd.randint(0, 5) == 5:
            self.title = "pang"
            self.app.game.title = "pang"
            self.app.tutorial.title = "pang"
            self.settings["title"] = "Pang Menu"
            self.app.game.settings["title"] = "Pang Game"
            self.app.update_screen()

    def play(self):
        self.app.scene = self.app.game

    def tutorial(self):
        self.app.scene = self.app.tutorial

    def quit(self):
        self.app.done = True

    def about(self):
        wb.open("pygame.org")
        self.description_open = True

    def handle_event(self, event):
        if self.description_open:
            if event.type == pg.MOUSEBUTTONDOWN:
                self.description_open = False
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    self.epilepsy_warning = True
                else:
                    self.description_open = False
            elif event.type == pg.KEYUP:
                if event.key == pg.K_ESCAPE:
                    self.epilepsy_warning = False
        else:
            if event.type == pg.MOUSEBUTTONDOWN:
                mouse_pos = self.app.get_mouse_pos()
                if self.title_rect.collidepoint(mouse_pos):
                    self.pong_title_easter_egg()
                if self.play_rect.collidepoint(mouse_pos):
                    self.play()
                if self.tutorial_rect.collidepoint(mouse_pos):
                    self.tutorial()
                if self.quit_rect.collidepoint(mouse_pos):
                    self.quit()
                if self.pygame_rect.collidepoint(mouse_pos):
                    self.about()
            elif event.type == pg.KEYDOWN:
                if not isinstance(self.option_selected, int):
                    self.option_selected = 0
                if event.key == pg.K_DOWN or event.key == pg.K_s:
                    self.option_selected += 1
                if event.key == pg.K_UP or event.key == pg.K_w:
                    self.option_selected -= 1

                if event.key == pg.K_RETURN:
                    if self.option_selected == 0:
                        self.play()
                    elif self.option_selected == 1:
                        self.tutorial()
                    elif self.option_selected == 2:
                        self.quit()

                if event.key == pg.K_ESCAPE:
                    self.epilepsy_warning = True
            elif event.type == pg.KEYUP:
                if event.key == pg.K_ESCAPE:
                    self.epilepsy_warning = False


class TutorialDialogue:
    def __init__(self, game: "Tutorial"):
        self.game = game
        self.stage = "0"
        self.dialogues: dict = {}
        self.generate_dialogues()
        self.dialogue_rect = None

    def is_paused(self):
        self.check_stage()
        if self.stage in {"0", "1", "2.get_easy", "2.get_hard", "2.get_long", "2.long_info", "4", "4.bad", "back1",
                          "return", "return2", "return3", "return4"}:
            self.game.screen.fill((0, 0, 0))
            return True
        return False

    def generate_dialogues(self):
        self.dialogues = {"0": f"welcome to {self.game.title}\n[press enter to continue]",
                          "1": "to move, use keys 'w' and 's'", "2": "",
                          "2.get_easy": "at the moment bot is easy\nlet make it harder",
                          "2.get_hard": "hard to win? ok i'll make bot slower",
                          "2.get_long": "nearly tie?\nmake it more interesting!",
                          "2.long_info": "now you can shoot[space], when bullet\nhits pallet. pallet can't move for a\n"
                                         "bit of time",
                          "3.1": "", "3.2": "", "3.3": "",
                          "4": "excellent, now you can play normal game",
                          "4.bad": "maybe try again?",
                          "return": "why did you return\nyou don't need tutorial anymore",
                          "return2": "i don't get it\nplay main game and enjoy your skills",
                          "return3": "it's getting boring, stop it!",
                          "return4": "ok you wanted this",
                          "close": ""}

    def get_text(self) -> str:
        return self.dialogues[self.stage]

    def update_stage(self):
        move_dict = {"0": "1", "1": "2", "2.get_easy": "3.1", "2.get_hard": "3.2", "2.get_long": "2.long_info",
                     "2.long_info": "3.3", "4": "back1", "4.bad": "back", "back1": "return", "return": "ret12",
                     "ret12": "return2", "return2": "ret23", "ret23": "return3", "return3": "ret34", "ret34": "return4",
                     "return4": "close"}
        if self.stage in move_dict:
            self.stage = move_dict[self.stage]

    def check_stage(self):
        if self.stage == "2":
            if self.game.player_score * 2 <= self.game.bot_score and self.game.bot_score >= 5:
                self.stage = "2.get_hard"
                self.game.bot.up_force = pg.Vector2(y=-5)
                self.game.bot.down_force = pg.Vector2(y=5)
                self.game.bot.up_force = pg.Vector2(y=-5)
                self.game.bot.down_force = pg.Vector2(y=5)
                self.game.bot.control_delay = 2
            elif self.game.player_score >= self.game.bot_score * 2 and self.game.player_score >= 7:
                self.stage = "2.get_easy"
                self.game.bot.up_force = pg.Vector2(y=-5)
                self.game.bot.down_force = pg.Vector2(y=5)
                self.game.bot.control_delay = 2
            elif self.game.bot_score >= 10:
                self.stage = "2.get_long"
        elif self.stage in {"3.1", "3.2", "3.3"}:
            if self.game.player_score > 10:
                if self.game.bot_score <= 10:
                    self.stage = "4"
                elif self.game.bot_score > 10:
                    self.stage = "4.bad"
        elif self.stage == "back1":
            self.game.app.scene = self.game.app.menu
            self.stage = "return"
        elif self.stage == "back":
            self.game.app.scene = self.game.app.menu
            self.game.player_score = 0
            self.game.bot_score = 0
            self.stage = "1"
        elif self.stage == "close":
            import sys
            sys.stdout.close()
            print("Did you want this?")
        elif self.stage in {"ret12", "ret23", "ret34"}:
            self.game.app.scene = self.game.app.menu
            self.update_stage()


class Tutorial(Game):
    def __init__(self, app):
        super().__init__(app)
        self.font = sp_sh.load_sprite_sheet("alphabet.png", "sprite_sheet.json", "box", 2)
        self.dialogue = TutorialDialogue(self)
        self.screen: pg.Surface = ...
        self.player_bullets: List[pg.Rect] = []
        self.bot_bullets: List[pg.Rect] = []
        self.player_stunned = 0
        self.bot_stunned = 0
        self.player_reload = 0
        self.bot_reload = 0
        self.stun_time = 90
        self.reload_time = 30
        self.escape_message = False
        self.dialogue.generate_dialogues()

        # uncomment for auto tutorial
        # self.player_score = 3
        # self.bot_score = 7

    @staticmethod
    def add_bullet(set_to_add: List[pg.Rect], thrower: pg.Rect):
        bullet = pg.Rect(0, 0, 5, 5)
        bullet.center = thrower.center
        set_to_add.append(bullet)

    def player_shoot(self):
        if self.player_reload == 0:
            self.add_bullet(self.player_bullets, self.player.rect)
            self.player_reload += self.reload_time

    def bot_shoot(self):
        if self.bot_reload == 0:
            self.add_bullet(self.bot_bullets, self.bot.rect)
            self.bot_reload += self.reload_time

    def initialize(self):
        super(Tutorial, self).initialize()
        self.font.generate()
        self.screen = self.app.get_scene_screen()
        self.settings["icon"] = self.sheet.get("logo")
        self.app.update_screen()

    def control_bot(self):
        if self.dialogue.stage == "3.3":
            if self.bot.rect.centerx - self.ball.hit_box.centerx <= 255:
                if self.bot_stunned > 0:
                    return
                if self.bot.hit_box.centery > self.ball.hit_box.centery:
                    self.bot.control(1)
                if self.bot.hit_box.centery < self.ball.hit_box.centery:
                    self.bot.control(2)
            # offensive
            else:
                # defensive
                if self.bot.hit_box.centery > self.player.hit_box.centery:
                    self.bot.control(1)
                    self.bot_shoot()
                if self.bot.hit_box.centery < self.player.hit_box.centery:
                    self.bot.control(2)
                    self.bot_shoot()
        else:
            super(Tutorial, self).control_bot()

    def update(self):
        if self.dialogue.is_paused():
            self.dialogue.generate_dialogues()
        else:
            super(Tutorial, self).update()
            for pl_b_index in range(len(self.player_bullets)):
                if self.bot.hit_box.colliderect(self.player_bullets[pl_b_index]):
                    self.bot_stunned += self.stun_time
                    self.player_bullets.pop(pl_b_index)
                    break
                self.player_bullets[pl_b_index].x += 5
                if not self.max_bounds.contains(self.player_bullets[pl_b_index]):
                    self.player_bullets.pop(pl_b_index)
                    break

            for bt_b_index in range(len(self.bot_bullets)):
                if self.player.hit_box.colliderect(self.bot_bullets[bt_b_index]):
                    self.player_stunned += self.stun_time
                    self.bot_bullets.pop(bt_b_index)
                    break
                self.bot_bullets[bt_b_index].x -= 5
                if not self.max_bounds.contains(self.bot_bullets[bt_b_index]):
                    self.bot_bullets.pop(bt_b_index)
                    break

            if self.player_reload > 0:
                self.player_reload -= 1

            if self.bot_reload > 0:
                self.bot_reload -= 1

            if self.player_stunned > 0:
                self.player_stunned -= 1
                self.player.image = self.pl_disabled_img
            else:
                self.player.image = self.pl_img

            if self.bot_stunned > 0:
                self.bot_stunned -= 1
                self.bot.image = self.pl_disabled_img
            else:
                self.bot.image = self.pl_img

    def draw(self):
        if self.dialogue.is_paused():
            if self.escape_message:
                self.screen.fill((rd.randint(0, 255), rd.randint(0, 255), rd.randint(0, 255)))
            self.dialogue.dialogue_rect = self.render_text(
                surface=self.screen,
                text=self.dialogue.get_text(),
                pos=(0, 0),
                right_offset=6, down_offset=2,
                font=self.font,
                calculate_offset=True,
                space_offset=40
            )
            return self.screen
        else:
            ret = super(Tutorial, self).draw()
            for pl_bullet in self.player_bullets:
                pg.draw.rect(ret, (255, 0, 0), pl_bullet)
            for bt_bullet in self.bot_bullets:
                pg.draw.rect(ret, (255, 0, 0), bt_bullet)
            return ret

    # noinspection PyCallingNonCallable
    def handle_input(self, k_id: int):
        if not self.dialogue.is_paused():
            if self.dialogue.stage == "3.3":
                if self.player_stunned == 0:
                    super(Tutorial, self).handle_input(k_id)
            else:
                super(Tutorial, self).handle_input(k_id)
        else:
            pass

    def handle_mouse_press(self, key: int, pos: Tuple[int, int]):
        super(Tutorial, self).handle_mouse_press(key, pos)

    # noinspection PyCallingNonCallable
    def handle_event(self, event):
        if not self.dialogue.is_paused():
            super(Tutorial, self).handle_event(event)
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_SPACE:
                    if self.dialogue.stage == "3.3":
                        self.player_shoot()
        else:
            with switch(event.type):
                if case(pg.KEYDOWN):
                    if event.key == pg.K_RETURN:
                        self.dialogue.update_stage()
                    elif event.key == pg.K_ESCAPE:
                        self.escape_message = True
                elif case(pg.KEYUP):
                    if event.key == pg.K_ESCAPE:
                        self.escape_message = False
                elif case(pg.MOUSEBUTTONDOWN):
                    self.dialogue.update_stage()
