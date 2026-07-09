package custom;

import robocode.*;
import robocode.util.Utils;
import java.awt.*;

public class MyTank extends AdvancedRobot {
    private double moveDirection = 1;
    
    public void run() {
        // Set colors
        setBodyColor(Color.BLUE);
        setGunColor(Color.RED);
        setRadarColor(Color.YELLOW);
        
        // Independent movement
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        
        while (true) {
            // Very simple movement - just move and turn
            setAhead(100 * moveDirection);
            setTurnRight(20);
            setTurnRadarRight(45);
            
            execute();
            
            // Occasionally change direction
            if (Math.random() < 0.1) {
                moveDirection *= -1;
            }
        }
    }
    
    public void onScannedRobot(ScannedRobotEvent e) {
        // Simple direct targeting
        double gunTurnAmt = Utils.normalRelativeAngleDegrees(
            getHeading() + e.getBearing() - getGunHeading());
        setTurnGunRight(gunTurnAmt);
        
        // Fire based on distance
        double bulletPower = 1.0;
        if (e.getDistance() < 200) {
            bulletPower = 2.0;
        }
        if (e.getDistance() < 100) {
            bulletPower = 3.0;
        }
        
        setFire(bulletPower);
        
        // Keep radar on target
        double radarTurnAmt = Utils.normalRelativeAngleDegrees(
            getHeading() + e.getBearing() - getRadarHeading());
        setTurnRadarRight(radarTurnAmt);
        
        execute();
    }
    
    public void onHitByBullet(HitByBulletEvent e) {
        // Simple evasion
        setTurnRight(90);
        setAhead(100);
        moveDirection *= -1;
        execute();
    }
    
    public void onHitWall(HitWallEvent e) {
        // Simple wall handling
        setBack(50);
        setTurnRight(90);
        moveDirection *= -1;
        execute();
    }
    
    public void onHitRobot(HitRobotEvent e) {
        // Back up and fire
        setBack(50);
        setFire(3.0);
        execute();
    }
}