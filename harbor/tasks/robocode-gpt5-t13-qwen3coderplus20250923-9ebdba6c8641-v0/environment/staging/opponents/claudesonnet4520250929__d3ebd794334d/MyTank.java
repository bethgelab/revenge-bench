package custom;

import robocode.*;
import java.awt.Color;

/**
 * MyTank - Round 9 strategy
 * Based on Round 4 winning strategy with incremental improvements
 * Strategy: Circle strafe movement with linear targeting
 * Round 8: Added randomness in strafe angle (85-95 degrees)
 * Round 9: Added bullet dodging based on enemy energy drop
 */
public class MyTank extends AdvancedRobot {
    private int moveDirection = 1;
    private double strafeAngle = 90;
    private double previousEnergy = 100.0;
    
    public void run() {
        // Set colors
        setBodyColor(Color.blue);
        setGunColor(Color.red);
        setRadarColor(Color.yellow);
        
        // Independent gun and radar movement
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        
        // Initialize random strafe angle (85-95 degrees)
        strafeAngle = 85 + Math.random() * 10;
        
        while (true) {
            // Continuous radar sweep
            setTurnRadarRight(360);
            execute();
        }
    }
    
    public void onScannedRobot(ScannedRobotEvent e) {
        // Radar lock - keep radar on enemy
        double radarTurn = getHeading() + e.getBearing() - getRadarHeading();
        setTurnRadarRight(normalizeBearing(radarTurn));
        
        // Bullet dodging: detect enemy fire by energy drop
        double energyDrop = previousEnergy - e.getEnergy();
        if (energyDrop > 0 && energyDrop <= 3.0) {
            // Enemy fired! Change direction to dodge
            moveDirection *= -1;
            // Also slightly adjust strafe angle
            strafeAngle = 85 + Math.random() * 10;
        }
        previousEnergy = e.getEnergy();
        
        // Movement: Circle strafe around enemy with slight randomness
        double absoluteBearing = getHeading() + e.getBearing();
        double turnAmount = normalizeBearing(absoluteBearing - getHeading() + strafeAngle - (15 * moveDirection));
        setTurnRight(turnAmount);
        
        // Move forward/backward based on distance
        if (e.getDistance() > 200) {
            setAhead(100 * moveDirection);
        } else {
            setAhead(50 * moveDirection);
        }
        
        // Linear targeting: predict where enemy will be
        double firePower = Math.min(3.0, Math.max(0.1, 400 / e.getDistance()));
        double bulletSpeed = 20 - 3 * firePower;
        double timeToHit = e.getDistance() / bulletSpeed;
        
        // Calculate predicted position
        double predictedX = e.getVelocity() * Math.sin(Math.toRadians(e.getHeading())) * timeToHit;
        double predictedY = e.getVelocity() * Math.cos(Math.toRadians(e.getHeading())) * timeToHit;
        double predictedBearing = Math.atan2(predictedX, predictedY);
        
        // Aim at predicted position
        double gunTurn = normalizeBearing(absoluteBearing + Math.toDegrees(predictedBearing) - getGunHeading());
        setTurnGunRight(gunTurn);
        
        // Fire when gun is aligned
        if (Math.abs(gunTurn) < 20) {
            setFire(firePower);
        }
        
        execute();
    }
    
    public void onHitWall(HitWallEvent e) {
        // Reverse direction when hitting wall
        moveDirection *= -1;
        // Slightly adjust strafe angle on wall hit
        strafeAngle = 85 + Math.random() * 10;
    }
    
    public void onHitRobot(HitRobotEvent e) {
        // Fire and reverse when hitting robot
        if (e.isMyFault()) {
            setFire(3);
            moveDirection *= -1;
        }
    }
    
    // Normalize bearing to [-180, 180]
    private double normalizeBearing(double angle) {
        while (angle > 180) angle -= 360;
        while (angle < -180) angle += 360;
        return angle;
    }
}