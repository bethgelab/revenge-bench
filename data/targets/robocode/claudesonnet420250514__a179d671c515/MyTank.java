package custom;

import robocode.util.*;
import robocode.*;
import java.awt.Color;

public class MyTank extends AdvancedRobot {
    private int moveDirection = 1;
    private double enemyEnergy = 100.0;
    private boolean enemyFound = false;
    private double enemyBearing = 0;
    private long lastScanTime = 0;
    
    public void run() {
        // Set colors
        setBodyColor(Color.blue);
        setGunColor(Color.black);
        setRadarColor(Color.yellow);
        setBulletColor(Color.red);
        setScanColor(Color.green);
        
        // Independent movement of gun and radar
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        
        while (true) {
            // Smart radar management
            if (!enemyFound || getTime() - lastScanTime > 5) {
                // Sweep for enemies if none found or lost track
                setTurnRadarRight(45);
                enemyFound = false;
            }
            
            // Optimized movement pattern - balanced frequency
            if (getTime() % 18 == 0) {  // Sweet spot between R7's 20 and R8's 15
                // Change direction periodically
                moveDirection *= -1;
            }
            
            // Balanced movement distance and turning
            double moveDistance = 90 + (getTime() % 4) * 40; // 90-210 distance (balanced variation)
            double turnAngle = 18 + (getTime() % 5) * 8; // 18-50 degrees (balanced range)
            
            // Enhanced wall avoidance - optimized margin
            double margin = 90; // Sweet spot between R7's 80 and R8's 100
            if (getX() < margin || getX() > getBattleFieldWidth() - margin ||
                getY() < margin || getY() > getBattleFieldHeight() - margin) {
                // Near wall, turn toward center
                double centerX = getBattleFieldWidth() / 2;
                double centerY = getBattleFieldHeight() / 2;
                double angleToCenter = Math.toDegrees(Math.atan2(centerX - getX(), centerY - getY()));
                setTurnRight(Utils.normalRelativeAngle(angleToCenter - getHeading()));
                moveDistance = Math.min(moveDistance, 110); // Balanced speed reduction
            }
            
            setAhead(moveDistance * moveDirection);
            setTurnRight(turnAngle * moveDirection);
            
            execute();
        }
    }
    
    public void onScannedRobot(ScannedRobotEvent e) {
        enemyFound = true;
        lastScanTime = getTime();
        enemyBearing = e.getBearingRadians();
        
        // Optimized energy-based power selection - balanced aggression
        double distance = e.getDistance();
        double firePower;
        if (distance < 135) {  // Sweet spot between R7's 150 and R8's 120
            // Very close range - maximum power
            firePower = Math.min(3.0, getEnergy() / 3);
        } else if (distance < 290) {  // Sweet spot between R7's 300 and R8's 280
            // Close range - high power
            firePower = Math.min(2.5, getEnergy() / 4);
        } else if (distance < 490) {  // Sweet spot between R7's 500 and R8's 480
            // Medium range - moderate power
            firePower = Math.min(2.0, getEnergy() / 5);
        } else {
            // Long range - lower power for accuracy
            firePower = Math.min(1.5, getEnergy() / 6);
        }
        
        // Ensure minimum power
        firePower = Math.max(0.1, firePower);
        
        // Enhanced predictive targeting with R8's velocity factor improvement
        double absoluteBearing = getHeadingRadians() + e.getBearingRadians();
        double enemyX = getX() + distance * Math.sin(absoluteBearing);
        double enemyY = getY() + distance * Math.cos(absoluteBearing);
        
        // Improved lead calculation with velocity factor
        double deltaTime = 0;
        double predictedX = enemyX, predictedY = enemyY;
        if (e.getVelocity() != 0) {
            deltaTime = distance / (20 - 3 * firePower);
            // Keep R8's velocity factor improvement
            double velocityFactor = Math.min(1.2, Math.abs(e.getVelocity()) / 8.0);
            predictedX = enemyX + Math.sin(e.getHeadingRadians()) * e.getVelocity() * deltaTime * velocityFactor;
            predictedY = enemyY + Math.cos(e.getHeadingRadians()) * e.getVelocity() * deltaTime * velocityFactor;
        }
        
        // Calculate angle to predicted position
        double theta = Utils.normalAbsoluteAngle(Math.atan2(
            predictedX - getX(), predictedY - getY()));
        
        // Turn gun to target
        setTurnGunRightRadians(Utils.normalRelativeAngle(
            theta - getGunHeadingRadians()));
        
        // Balanced firing accuracy - between R7's 8 and R8's 6
        if (Math.abs(getGunTurnRemaining()) < 7 && getEnergy() > firePower + 1) {
            setFire(firePower);
        }
        
        // Energy drop detection for dodging - keep R8's variable angles but moderate
        if (enemyEnergy > e.getEnergy()) {
            // Enemy fired, dodge with balanced variation
            double dodgeAngle = 85 + (getTime() % 3) * 15; // 85-115 degrees (more moderate)
            setTurnRight(dodgeAngle * moveDirection);
            setAhead(145 * moveDirection); // Balanced distance
        }
        enemyEnergy = e.getEnergy();
        
        // Optimized radar lock - balanced aggression
        double radarTurn = Utils.normalRelativeAngle(absoluteBearing - getRadarHeadingRadians());
        setTurnRadarRightRadians(radarTurn * 1.65);  // Sweet spot between R7's 1.5 and R8's 1.8
    }
    
    public void onHitByBullet(HitByBulletEvent e) {
        // Enhanced evasive maneuvers - balanced variation
        moveDirection *= -1;
        double evasionAngle = 110 + (getTime() % 3) * 15; // 110-140 degrees (more moderate)
        setTurnRight(evasionAngle - e.getBearing());
        setAhead(155 * moveDirection);  // Balanced distance
    }
    
    public void onHitWall(HitWallEvent e) {
        // Reverse and turn away from wall with moderate variation
        moveDirection *= -1;
        double wallTurnAngle = 170 + (getTime() % 3) * 15; // 170-200 degrees (more moderate)
        setTurnRight(wallTurnAngle);
        setAhead(110 * moveDirection);  // Balanced distance
    }
    
    public void onHitRobot(HitRobotEvent e) {
        // Enhanced close combat - balanced aggression
        if (e.isMyFault()) {
            setTurnRight(12);  // Between R7's 10 and R8's 15
            setBack(110);      // Between R7's 100 and R8's 120
        }
        // Fire at close range if we have energy - balanced threshold
        if (getEnergy() > 4.5) {  // Between R7's 5 and R8's 4
            setFire(2.6);       // Between R7's 2.5 and R8's 2.8
        }
    }
}