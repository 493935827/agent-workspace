#!/usr/bin/env python3
import argparse
from serial_service import SerialService
p=argparse.ArgumentParser(); p.add_argument('--port'); p.add_argument('--baud',type=int,default=115200); p.add_argument('--tcp',type=int,default=8888); p.add_argument('--control',type=int,default=8889); p.add_argument('--log'); a=p.parse_args(); s=SerialService(port=a.port,baud=a.baud,tcp=a.tcp,control=a.control,log=a.log).start(); print(f'managed service running: raw={s.tcp_port} control={s.control_port}',flush=True)
try:s.stop.wait()
except KeyboardInterrupt:pass
finally:s.close()
