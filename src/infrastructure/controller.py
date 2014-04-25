import threading
import datetime
import logging

from domain.commands import *

class MachineState(object):
    def __init__(self,xyz = [0.0,0.0,0.0], speed = 1.0):
        self.x, self.y, self.z = xyz
        self.speed = speed

    @property
    def xy(self):
        return [self.x,self.y]

    @property
    def xyz(self):
        return [self.x,self.y, self.z]

    def set_state(self, cordanates, speed):
        self.x, self.y, self.z = cordanates
        self.speed = speed

class MachineError(object):
    def __init__(self,message):
        self.timestamp = datetime.datetime.now()
        self.message = message

class MachineStatus(object):
    def __init__(self, status_call_back = None):
        self._status_call_back = status_call_back
        self._current_layer = 0
        self._laser_state = False
        self._waiting_for_drips = True
        self._height = 0.0
        self._errors = []
        self._start_time = datetime.datetime.now()
        self._stop_time = None
        self._complete = False
        self._drips = 0

    def _update(self):
        if self._status_call_back:
            self._status_call_back(self.status())

    def drip_call_back(self, drips, height):
        self._height = height
        self._drips = drips
        self._update()

    def add_layer(self):
        self._current_layer += 1
        self._update()

    def add_error(self, error):
        self._errors.append(error)
        self._update()

    def set_waiting_for_drips(self):
        self._waiting_for_drips = True
        self._update()

    def set_not_waiting_for_drips(self):
        self._waiting_for_drips = False
        self._update()

    def set_layers_ahead(self):
        self._update()
        pass

    def set_complete(self):
        self._complete = True
        self._update()

    def _elapsed_time(self):
        return datetime.datetime.now() - self._start_time

    def _status(self):
        if self._complete:
            return 'Complete'
        if (self._drips == 0 and self._current_layer == 0):
            return 'Starting'
        else:
            return 'Running'
    
    def _formatted_errors(self):
        return [ {'time': error.timestamp, 'message' : error.message} for error in self._errors ]

    def status(self): 
        return { 
            'start_time' : self._start_time,
            'elapsed_time' : self._elapsed_time(),
            'current_layer' : self._current_layer,
            'status': self._status(),
            'errors' : self._formatted_errors(),
            'waiting_for_drips' : self._waiting_for_drips,
            'height' : self._height,
            'drips' : self._drips,

        }


class Controller(threading.Thread,):
    def __init__(self, laser_control, path_to_audio,audio_writer,layer_generator,zaxis = None,status_call_back = None):
        threading.Thread.__init__(self)
        self.deamon = True

        self._shutting_down = False
        self.running = False
        self.starting = True
        
        self._laser_control = laser_control
        self._path_to_audio = path_to_audio
        self._audio_writer = audio_writer
        self._layer_generator = layer_generator
        
        self.state = MachineState()
        self._status = MachineStatus(status_call_back)
        self._zaxis = zaxis
        if self._zaxis:
            self._zaxis.set_drip_call_back(self._status.drip_call_back)
        self._abort_current_command = False
        logging.info("Starting print")

    def change_generator(self, layer_generator):
        self._layer_generator = layer_generator
        self._abort_current_command = True

    def _process_layers(self):
        going = True
        while going:
            try:
                logging.debug("New Layer")
                layer = self._layer_generator.next()
                if self._shutting_down:
                    return
                if self._zaxis:
                    while self._zaxis.current_z_location_mm() < layer.z:
                        logging.info("Controller: Waiting for drips")
                        self._status.set_waiting_for_drips()
                        if self._shutting_down:
                            return
                        self._laser_control.set_laser_off()
                        self._move_lateral(self.state.xy, self.state.z,self.state.speed)
                self._status.set_not_waiting_for_drips()
                for command in layer.commands:
                    if self._shutting_down:
                        return
                    if self._abort_current_command:
                        self._abort_current_command = False
                        break
                    if type(command) == LateralDraw:
                        logging.debug('Lateral Draw: %s' % command)
                        if self.state.xy != command.start:
                            self._laser_control.set_laser_off()
                            self._move_lateral(command.start,layer.z,command.speed)
                        self._laser_control.set_laser_on()
                        self._move_lateral(command.end, layer.z, command.speed )
                    elif type(command) == LateralMove:
                        logging.debug('Lateral Move: %s' % command)
                        self._laser_control.set_laser_off()
                        self._move_lateral(command.end, layer.z, command.speed)
                self._status.add_layer()
            except StopIteration:
                going = False

    def run(self):
        self.running = True
        if self._zaxis:
            self._zaxis.start()
        self.starting = False
        self._process_layers()
        self._status.set_complete()
        self._terminate()

    def _terminate(self):
        self._shutting_down = True
        if self._zaxis:
            try:
                self._zaxis.stop()
            except Exception as ex:
                logging.error(ex)
        try:
            self._audio_writer.close()
        except Exception as ex:
            logging.error(ex)
        self.running = False

    def get_status(self):
        return self._status.status()

    def stop(self):
        logging.warning("Shutdown requested")
        self._shutting_down = True

    def _move_lateral(self,(to_x,to_y), to_z,speed):
        to_xyz = [to_x,to_y,to_z]
        path = self._path_to_audio.process(self.state.xyz,to_xyz , speed)
        modulated_path = self._laser_control.modulate(path)
        self._audio_writer.write_chunk(modulated_path)
        self.state.set_state(to_xyz,speed)