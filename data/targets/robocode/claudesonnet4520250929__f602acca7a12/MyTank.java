package custom;

import robocode.Robot;
import robocode.ScannedRobotEvent;
import java.awt.*;

public class MyTank extends Robot {
    private double enemyBearing = 0;
    private double enemyDistance = 0;
    private boolean movingForward = true;
    
    public void run() {
        setColors(Color.blue, Color.blue, Color.blue);
        
        while(true) {
            // Keep radar spinning to track enemy
            turnRadarRight(360);
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        enemyBearing = e.getBearing();
        enemyDistance = e.getDistance();
        
        // Perpendicular movement - move at right angles to enemy
        // This makes us harder to hit
        double absoluteBearing = getHeading() + enemyBearing;
        double perpendicularAngle = absoluteBearing + 90;
        
        // Turn perpendicular to enemy
        double turnAngle = perpendicularAngle - getHeading();
        // Normalize angle to -180 to 180
        while (turnAngle > 180) turnAngle -= 360;
        while (turnAngle < -180) turnAngle += 360;
        
        turnRight(turnAngle);
        
        // Move forward or backward randomly to be unpredictable
        if (Math.random() < 0.05) {
            movingForward = !movingForward;
        }
        
        if (movingForward) {
            ahead(100);
        } else {
            back(100);
        }
        
        // Aim gun at enemy with lead prediction
        double gunTurnAngle = getHeading() + enemyBearing - getGunHeading();
        while (gunTurnAngle > 180) gunTurnAngle -= 360;
        while (gunTurnAngle < -180) gunTurnAngle += 360;
        turnGunRight(gunTurnAngle);
        
        // Fire with power based on distance
        double firePower = 1.0;
        if (enemyDistance < 200) {
            firePower = 3.0;  // High power at close range
        } else if (enemyDistance < 400) {
            firePower = 2.0;  // Medium power at medium range
        }
        
        fire(firePower);
    }
}