package custom;

import robocode.AdvancedRobot;
import robocode.HitRobotEvent;
import robocode.ScannedRobotEvent;
import robocode.WinEvent;
import static robocode.util.Utils.normalRelativeAngleDegrees;

import java.awt.*;

public class MyTank extends AdvancedRobot {
    int count = 0; // Keeps track of how long we've been searching for our target
    double gunTurnAmt; // How much to turn our gun when searching
    String trackName; // Name of the robot we're currently tracking

    public void run() {
        // Set colors
        setBodyColor(new Color(150, 75, 0)); // Brown
        setGunColor(new Color(100, 100, 100)); // Gray
        setRadarColor(new Color(0, 0, 200)); // Blue
        setScanColor(Color.white);
        setBulletColor(Color.red);

        // Prepare gun
        trackName = null; // Initialize to not tracking anyone
        setAdjustGunForRobotTurn(true); // Keep the gun still when we turn
        setAdjustRadarForRobotTurn(true); // Keep the radar still when we turn
        gunTurnAmt = 10; // Initialize gunTurn to 10

        // Loop forever
        while (true) {
            // turn the Gun (looks for enemy)
            turnGunRight(gunTurnAmt);
            // Keep track of how long we've been looking
            count++;
            // If we've haven't seen our target for 2 turns, look left
            if (count > 2) {
                gunTurnAmt = -10;
            }
            // If we still haven't seen our target for 5 turns, look right
            if (count > 5) {
                gunTurnAmt = 10;
            }
            // If we *still* haven't seen our target after 10 turns, find another target
            if (count > 11) {
                trackName = null;
            }
            
            // Add some movement to avoid being hit
            setMaxVelocity(6); // Set a good speed
            setTurnRight(5); // Slowly turn while moving
            ahead(100); // Move forward
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // If we have a target, and this isn't it, return immediately
        // so we can get more ScannedRobotEvents.
        if (trackName != null && !e.getName().equals(trackName)) {
            return;
        }

        // If we don't have a target, well, now we do!
        if (trackName == null) {
            trackName = e.getName();
            out.println("Tracking " + trackName);
        }
        // This is our target.  Reset count (see the run method)
        count = 0;
        
        // Calculate firepower based on distance - closer = more power
        double firepower = Math.min(3.0, Math.max(0.1, 100 / e.getDistance()));
        
        // Aim and fire
        gunTurnAmt = normalRelativeAngleDegrees(e.getBearing() + (getHeading() - getRadarHeading()));
        setTurnGunRight(gunTurnAmt);
        setFire(firepower);
        
        // If our target is far away, move toward it
        if (e.getDistance() > 200) {
            setTurnRight(e.getBearing());
            ahead(e.getDistance() - 150);
        }
        // If our target is very close, move away
        else if (e.getDistance() < 100) {
            setTurnRight(e.getBearing() + 180); // Turn away
            ahead(100); // Move away
        }
        
        execute(); // Execute all the commands together
    }

    public void onHitRobot(HitRobotEvent e) {
        // Only print if he's not already our target.
        if (trackName != null && !trackName.equals(e.getName())) {
            out.println("Tracking " + e.getName() + " due to collision");
        }
        // Set the target
        trackName = e.getName();
        
        // Fire with maximum power
        setFire(3);
        // Move away from the robot we hit
        back(50);
    }

    public void onWin(WinEvent e) {
        for (int i = 0; i < 50; i++) {
            turnRight(30);
            turnLeft(30);
        }
    }
}