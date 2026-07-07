package custom;

import robocode.Robot;
import robocode.ScannedRobotEvent;
import robocode.HitWallEvent;
import robocode.HitRobotEvent;
import robocode.BulletHitEvent;

public class MyTank extends Robot {
    private int direction = 1;
    private double moveAmount;
    private boolean peek = false;
    
    public void run() {
        // Set gun and radar to move independently
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        
        // Initialize moveAmount for wall following (like sample.Walls)
        moveAmount = Math.max(getBattleFieldWidth(), getBattleFieldHeight());
        
        // Move to a wall initially
        turnLeft(getHeading() % 90);
        ahead(moveAmount);
        
        // Turn gun inward and start wall following
        peek = true;
        turnGunRight(90);
        turnRight(90);
        
        while (true) {
            // Look before we turn when ahead() completes
            peek = true;
            // Move up the wall
            ahead(moveAmount);
            // Don't look now
            peek = false;
            // Turn to the next wall
            turnRight(90);
        }
    }
    
    public void onScannedRobot(ScannedRobotEvent e) {
        // Calculate absolute bearing to enemy
        double absoluteBearing = getHeading() + e.getBearing();
        
        // Turn gun to enemy
        double gunTurn = absoluteBearing - getGunHeading();
        
        // Normalize angle
        while (gunTurn > 180) gunTurn -= 360;
        while (gunTurn < -180) gunTurn += 360;
        
        turnGunRight(gunTurn);
        
        // Aggressive firing with validated optimal tolerance (35 degrees)
        if (Math.abs(gunTurn) < 35 && getGunHeat() == 0) {
            double bulletPower = 2.0;
            if (getEnergy() < 6) bulletPower = 1.0;
            fire(bulletPower);
        }
        
        // Additional scan when peeking (like sample.Walls)
        if (peek) {
            scan();
        }
    }
    
    public void onHitWall(HitWallEvent e) {
        direction *= -1;
        back(30);
        turnRight(60 * direction);
    }
    
    public void onHitRobot(HitRobotEvent e) {
        // If enemy is in front, back up; if behind, move forward
        if (e.getBearing() > -90 && e.getBearing() < 90) {
            back(100);
        } else {
            ahead(100);
        }
        fire(2.0);
    }
    
    public void onBulletHit(BulletHitEvent e) {
        // Success!
    }
}