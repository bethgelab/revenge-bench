package custom;

import robocode.Robot;
import robocode.ScannedRobotEvent;
import robocode.HitByBulletEvent;
import robocode.HitRobotEvent;
import robocode.WinEvent;
import static robocode.util.Utils.normalRelativeAngleDegrees;

import java.awt.*;

public class MyTank extends Robot {
    private boolean movingForward = true;
    private int count = 0;
    private double gunTurnAmt = 10;
    private String targetName = null;
    private double targetX = 0;
    private double targetY = 0;
    private double lastTargetDistance = 0;

    public void run() {
        // Set colors
        setBodyColor(Color.orange);
        setGunColor(Color.red);
        setRadarColor(Color.green);
        setScanColor(Color.yellow);
        setBulletColor(Color.blue);

        // Set the turn rate for the radar to be faster
        setAdjustRadarForRobotTurn(true);
        setAdjustGunForRobotTurn(true);

        while(true) {
            // If we have no target or haven't seen our target recently, look for enemy
            if (targetName == null || count > 10) {
                // Turn the gun to scan
                turnGunRight(gunTurnAmt);
                count++;
                
                if (count > 2) {
                    gunTurnAmt = -10;
                }
                if (count > 5) {
                    gunTurnAmt = 10;
                }
                if (count > 11) {
                    targetName = null;
                    count = 0;
                }
            } else {
                // We have a target, move in a more evasive pattern to avoid being an easy target
                // Use a combination of forward/backward and turning to be less predictable
                if (movingForward) {
                    ahead(100);
                } else {
                    back(100);
                }
                
                // Add some random turning to make movement less predictable
                if (getTime() % 10 == 0) {
                    turnRight(Math.random() * 30 - 15); // Turn randomly between -15 and 15 degrees
                }
                
                // Toggle movement direction
                movingForward = !movingForward;
                
                // Turn the radar to keep tracking the target
                turnRadarRight(10);
            }
            
            // Execute the commands by scanning
            scan();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // If we have a target, and this isn't it, return immediately
        if (targetName != null && !e.getName().equals(targetName)) {
            return;
        }

        // If we don't have a target, now we do!
        if (targetName == null) {
            targetName = e.getName();
            out.println("Tracking " + targetName);
        }
        
        // This is our target. Reset count
        count = 0;
        
        // Store target position for better prediction
        double absoluteBearing = getHeading() + e.getBearing();
        targetX = getX() + e.getDistance() * Math.sin(Math.toRadians(absoluteBearing));
        targetY = getY() + e.getDistance() * Math.cos(Math.toRadians(absoluteBearing));
        lastTargetDistance = e.getDistance();
        
        // Calculate firepower based on distance and our energy
        double firepower = 3; // Maximum firepower for close targets
        if (e.getDistance() > 200) {
            firepower = 1; // Lower firepower for distant targets to conserve energy
        } else if (e.getDistance() > 100) {
            firepower = 2;
        }
        
        // Limit firepower based on our energy level
        if (getEnergy() < 10 && firepower > 1) {
            firepower = 1;
        }

        // Calculate gun turn to aim at the enemy
        double gunTurn = normalRelativeAngleDegrees(e.getBearing() + (getHeading() - getGunHeading()));
        turnGunRight(gunTurn);

        // Fire with calculated firepower
        fire(firepower);
        
        // If the target is far away, move toward it
        if (e.getDistance() > 150) {
            double turn = e.getBearing();
            turnRight(turn);
            ahead(e.getDistance() - 140);
        } 
        // If the target is too close, move away
        else if (e.getDistance() < 100) {
            if (e.getBearing() > -90 && e.getBearing() <= 90) {
                back(40);
            } else {
                ahead(40);
            }
        }
        
        // Keep scanning
        scan();
    }

    public void onHitByBullet(HitByBulletEvent e) {
        // Calculate angle to move perpendicular to the bullet (dodge)
        double angle = normalRelativeAngleDegrees(90 - (getHeading() - e.getHeading()));
        turnRight(angle);
        ahead(50);
        
        // Change direction to be less predictable
        movingForward = !movingForward;
    }

    public void onHitRobot(HitRobotEvent e) {
        // Only print if it's not already our target
        if (targetName != null && !targetName.equals(e.getName())) {
            out.println("Tracking " + e.getName() + " due to collision");
        }
        
        // Set the target
        targetName = e.getName();
        
        // Fire with maximum power if it's close
        if (e.getBearing() > -90 && e.getBearing() <= 90) {
            turnGunRight(e.getBearing() + (getHeading() - getGunHeading()));
            fire(3);
            back(50);
        } else {
            ahead(50);
        }
    }

    public void onHitWall() {
        // Move away from the wall
        back(50);
        turnRight(45);
        
        // Change direction to be less predictable
        movingForward = !movingForward;
    }
    
    public void onWin(WinEvent e) {
        // Do a victory dance
        for (int i = 0; i < 20; i++) {
            turnRight(18);
            turnLeft(18);
        }
    }
}