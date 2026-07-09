package custom;

import robocode.Robot;
import robocode.ScannedRobotEvent;
import robocode.HitByBulletEvent;
import robocode.HitWallEvent;

public class MyTank extends Robot {
    int moveDirection = 1;
    
    public void run() {
        while(true) {
            // Better movement pattern - move in squares instead of just back/forth
            ahead(100 * moveDirection);
            turnRight(90);
            
            // Scan for enemies
            turnGunRight(360);
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // Improved firing strategy based on distance and energy
        if (e.getDistance() < 100 && getEnergy() > 50) {
            fire(3); // Fire hard at close range
        } else if (e.getDistance() < 200 && getEnergy() > 30) {
            fire(2); // Medium power at medium range
        } else {
            fire(1); // Conservative firing
        }
    }
    
    public void onHitByBullet(HitByBulletEvent e) {
        // Evasive maneuver - change direction when hit
        moveDirection *= -1;
        turnRight(90);
        ahead(50 * moveDirection);
    }
    
    public void onHitWall(HitWallEvent e) {
        // When hitting wall, reverse direction
        moveDirection *= -1;
        turnRight(90);
    }
}