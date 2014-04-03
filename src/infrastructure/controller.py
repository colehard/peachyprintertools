from domain.commands import *

class MachineState(object):
    def __init__(self,xy = [0.0,0.0], z = 0.0):
        self.position = xy
        self._z = z

    def set_state(self, cordanates):
        self.position = cordanates

    @property
    def z(self):
        return 0.0

    @property
    def xy(self):
        return self.position


class Controller(object):
    def __init__(self, laser_control, path_to_audio,audio_writer,layer_generator,zaxis = None):
        self._laser_control = laser_control
        self._path_to_audio = path_to_audio
        self._audio_writer = audio_writer
        self._layer_generator = layer_generator
        self._zaxis = zaxis
        self.state = MachineState()

    def start(self):
        for layer in self._layer_generator:
            positional_refresh_required = True
            for command in layer.commands:
                if type(command) == LateralDraw:
                    if self.state.xy != command.start or positional_refresh_required:
                        self._laser_control.set_laser_off()
                        self._move_lateral(command.start,command.speed)
                        positional_refresh_required = False
                    self._laser_control.set_laser_on()
                    self._move_lateral(command.end, command.speed )
                elif type(command) == LateralMove:
                    self._laser_control.set_laser_off()
                    self._move_lateral(command.end, command.speed)
                    positional_refresh_required = False

    def _move_lateral(self,to_xy,speed):
        path = self._path_to_audio.process(self.state.xy, to_xy, speed)
        modulated_path = self._laser_control.modulate(path)
        self._audio_writer.write_chunk(modulated_path)
        self.state.set_state(to_xy)