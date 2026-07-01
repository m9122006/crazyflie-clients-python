# -*- coding: utf-8 -*-
"""
Example script to make the Crazyflie ascend vertically to 80cm (0.8m)
and hold altitude (hover) using the Crazyflie Python Library (cflib).

WARNING:
This script CANNOT be run without a positioning deck (e.g., Flow Deck v2, 
Z-ranger + Lighthouse/LPS). Without a deck, the drone's Kalman filter (EKF)
will not have coordinate feedback, causing the takeoff to fail or the drone 
to drift rapidly and crash.
"""

import logging
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander
from cflib.utils import uri_helper

# URI to the Crazyflie (adjust as needed for your radio configuration)
URI = uri_helper.uri_from_env(default='radio://0/80/2M/E7E7E7E7E7')

# Only output errors from the logging framework
logging.basicConfig(level=logging.ERROR)


def run_with_motion_commander(scf):
    """
    Method 1: Using the MotionCommander helper class.
    This is the simplest way to execute relative vertical movements.
    """
    print("--- Method 1: MotionCommander ---")
    
    # Arm the Crazyflie
    print("Arming Crazyflie...")
    scf.cf.supervisor.send_arming_request(True)
    time.sleep(1.0)
    
    # We initialize the MotionCommander with a default height of 0.8 meters (80cm)
    # The takeoff command will automatically ascend to this height.
    print("Taking off to 0.8 meters (80cm)...")
    with MotionCommander(scf, default_height=0.8) as mc:
        # Hover at 80cm for 5 seconds
        print("Holding altitude at 80cm...")
        time.sleep(5.0)
        
        print("Landing...")
        # Landing is performed automatically when exiting the context manager (with-block)
        # but you can also call mc.land() explicitly if not using context manager.


def run_with_high_level_commander(scf):
    """
    Method 2: Using the firmware's High-Level Commander.
    This offloads the trajectory generation to the drone's microcontroller (CMDHL task).
    """
    print("--- Method 2: High-Level Commander ---")
    cf = scf.cf
    commander = cf.high_level_commander

    # Arm the Crazyflie
    print("Arming Crazyflie...")
    cf.supervisor.send_arming_request(True)
    time.sleep(1.0)

    # Takeoff parameters: absolute_height = 0.8m, duration = 2.0s, yaw = 0.0
    print("Taking off to 0.8 meters in 2.0 seconds...")
    commander.takeoff(0.8, 2.0)
    
    # Wait for the takeoff to complete and hover for 5 seconds
    time.sleep(2.0 + 5.0)

    # Land: absolute_height = 0.0m, duration = 2.0s
    print("Landing...")
    commander.land(0.0, 2.0)
    time.sleep(2.0)

    # Stop the commander to release control
    commander.stop()


if __name__ == '__main__':
    # Initialize the low-level drivers
    cflib.crtp.init_drivers()

    print(f"Connecting to {URI}...")
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
        # We reset the estimator to ensure accurate positioning before takeoff
        print("Resetting estimator...")
        scf.cf.param.set_value('kalman.resetEstimation', '1')
        time.sleep(0.1)
        scf.cf.param.set_value('kalman.resetEstimation', '0')
        time.sleep(2.0)  # Wait for Kalman filter to stabilize

        # Choose your method here:
        run_with_motion_commander(scf)
        # OR:
        # run_with_high_level_commander(scf)
