package custom;

import robocode.*;
import java.awt.Color;

/**
 * MyTank - An improved bot with better movement, targeting, and radar lock
 * Round 2: Added wall avoidance to prevent getting cornered
 */
public class MyTank extends AdvancedRobot {
    private double enemyBearing;
    private double enemyDistance;
    private double enemyEnergy = 100;
    private double enemyVelocity;
    private int movementDirection = 1;
    private int radarDirection = 1;
    
    public void run() {
        // Set colors
        setBodyColor(Color.blue);
        setGunColor(Color.red);
        setRadarColor(Color.green);
        setBulletColor(Color.yellow);
        
        // Independent movement of gun, radar, and body
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        setAdjustRadarForRobotTurn(true);
        
        // Main loop
        while (true) {
            // Spin radar to find enemy
            setTurnRadarRight(360);
            execute();
        }
    }
    
    public void onScannedRobot(ScannedRobotEvent e) {
        // Track enemy data
        enemyBearing = e.getBearing();
        enemyDistance = e.getDistance();
        double newEnemyEnergy = e.getEnergy();
        enemyVelocity = e.getVelocity();
        
        // Radar lock - narrow beam tracking
        double radarTurn = getHeading() + e.getBearing() - getRadarHeading();
        setTurnRadarRight(normalizeBearing(radarTurn) * 2);
        
        // Movement - perpendicular/circular movement with wall avoidance
        performMovement(e);
        
        // Targeting and firing
        performTargeting(e);
        
        // Update enemy energy
        enemyEnergy = newEnemyEnergy;
        
        execute();
    }
    
    private void performMovement(ScannedRobotEvent e) {
        // Perpendicular movement - stay at optimal distance
        double optimalDistance = 300;
        
        // Check distance to walls
        double distanceToWall = Math.min(
            Math.min(getX(), getBattleFieldWidth() - getX()),
            Math.min(getY(), getBattleFieldHeight() - getY())
        );
        
        // If too close to wall, move away from it
        if (distanceToWall < 100) {
            // Calculate angle to center of battlefield
            double centerX = getBattleFieldWidth() / 2;
            double centerY = getBattleFieldHeight() / 2;
            double angleToCenter = Math.toDegrees(Math.atan2(centerX - getX(), centerY - getY()));
            double turnToCenter = normalizeBearing(angleToCenter - getHeading());
            
            // Turn towards center and move
            setTurnRight(turnToCenter);
            setAhead(100);
        } else {
            // Normal perpendicular movement
            // Turn perpendicular to enemy
            double turnAngle = e.getBearing() + 90 - (15 * movementDirection);
            setTurnRight(normalizeBearing(turnAngle));
            
            // Move forward or backward based on distance
            if (e.getDistance() > optimalDistance + 50) {
                setAhead(100 * movementDirection);
            } else if (e.getDistance() < optimalDistance - 50) {
                setBack(100 * movementDirection);
            } else {
                setAhead(100 * movementDirection);
            }
            
            // Change direction occasionally to be unpredictable
            if (Math.random() < 0.05) {
                movementDirection *= -1;
            }
        }
    }
    
    private void performTargeting(ScannedRobotEvent e) {
        // Predictive targeting - lead the target
        double bulletPower = chooseBulletPower(e.getDistance());
        double bulletSpeed = 20 - 3 * bulletPower;
        
        // Calculate time for bullet to reach enemy
        double timeToHit = e.getDistance() / bulletSpeed;
        
        // Predict enemy position
        double predictedBearing = e.getBearing() + 
            (e.getVelocity() * Math.sin(Math.toRadians(e.getHeading() - getHeading())) * timeToHit / e.getDistance());
        
        // Aim gun
        double gunTurn = getHeading() + predictedBearing - getGunHeading();
        setTurnGunRight(normalizeBearing(gunTurn));
        
        // Fire when gun is aligned
        if (Math.abs(getGunTurnRemaining()) < 10) {
            setFire(bulletPower);
        }
    }
    
    private double chooseBulletPower(double distance) {
        // Energy management - adjust fire power based on distance and our energy
        if (getEnergy() < 20) {
            return 1.0;
        } else if (distance < 100) {
            return 3.0;
        } else if (distance < 300) {
            return 2.5;
        } else if (distance < 500) {
            return 2.0;
        } else {
            return 1.5;
        }
    }
    
    public void onHitByBullet(HitByBulletEvent e) {
        // Change direction when hit
        movementDirection *= -1;
        setAhead(100 * movementDirection);
    }
    
    public void onHitWall(HitWallEvent e) {
        // Reverse direction when hitting wall
        movementDirection *= -1;
        setAhead(100 * movementDirection);
    }
    
    public void onHitRobot(HitRobotEvent e) {
        // If we hit enemy, back up and fire
        if (e.getBearing() > -90 && e.getBearing() < 90) {
            setBack(100);
        } else {
            setAhead(100);
        }
        setFire(3);
    }
    
    // Normalize bearing to [-180, 180]
    private double normalizeBearing(double angle) {
        while (angle > 180) angle -= 360;
        while (angle < -180) angle += 360;
        return angle;
    }
}