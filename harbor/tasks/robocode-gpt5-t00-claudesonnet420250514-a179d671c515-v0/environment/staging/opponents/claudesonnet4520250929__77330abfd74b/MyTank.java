package custom;

import robocode.*;
import java.awt.Color;

/**
 * MyTank - Round 15: Back to basics - pure circular movement
 * Round 10: 96% win rate (24/25 battles) - BEST
 * Round 14: 72% win rate (18/25 battles) - declining
 * 
 * Analysis: Wall smoothing has been hurting performance since Round 10
 * Solution: Remove wall smoothing entirely, rely on collision handlers
 * Strategy: Pure circular movement + Direct targeting (Round 10 approach)
 */
public class MyTank extends AdvancedRobot {
    private int moveDirection = 1;
    private int tickCount = 0;
    
    public void run() {
        // Set colors
        setBodyColor(Color.blue);
        setGunColor(Color.red);
        setRadarColor(Color.yellow);
        setBulletColor(Color.red);
        setScanColor(Color.yellow);
        
        // Independent movement
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        
        // Main loop
        while (true) {
            tickCount++;
            setTurnRadarRight(360);
            execute();
        }
    }
    
    public void onScannedRobot(ScannedRobotEvent e) {
        // Radar lock
        double radarTurn = normalizeAngle(getHeading() + e.getBearing() - getRadarHeading());
        setTurnRadarRight(radarTurn * 2.0);
        
        double absoluteBearing = getHeading() + e.getBearing();
        double distance = e.getDistance();
        
        // PURE CIRCULAR MOVEMENT - no wall smoothing interference
        // This was our winning strategy in Round 10
        double turnAngle = normalizeAngle(absoluteBearing - getHeading() + 90 * moveDirection);
        setTurnRight(turnAngle);
        
        // Maintain optimal distance (150-350 range) with slight randomness
        double moveDistance = 50;
        if (tickCount % 20 < 10) {
            moveDistance = 60; // Add slight variation
        }
        
        if (distance > 350) {
            setAhead(100);
        } else if (distance < 150) {
            setBack(100);
        } else {
            setAhead(moveDistance);
        }
        
        // DIRECT TARGETING (proven to work)
        double gunTurn = normalizeAngle(absoluteBearing - getGunHeading());
        setTurnGunRight(gunTurn);
        
        // Fire power based on distance
        double power;
        if (distance < 100) {
            power = 3.0;
        } else if (distance < 300) {
            power = 2.0;
        } else {
            power = 1.5;
        }
        
        // Fire when well aligned with good energy management
        if (Math.abs(gunTurn) < 8 && getGunHeat() == 0 && getEnergy() > 5) {
            setFire(power);
        }
    }
    
    public void onHitByBullet(HitByBulletEvent e) {
        // Change direction when hit
        moveDirection *= -1;
        setTurnRight(90 * moveDirection);
    }
    
    public void onHitWall(HitWallEvent e) {
        // Reverse when hitting wall - let collision handler deal with walls
        moveDirection *= -1;
        setBack(100);
        setTurnRight(90 * moveDirection);
    }
    
    public void onHitRobot(HitRobotEvent e) {
        // Back away from collision
        setBack(100);
        moveDirection *= -1;
    }
    
    // Helper method to normalize angles to -180 to 180
    private double normalizeAngle(double angle) {
        while (angle > 180) angle -= 360;
        while (angle < -180) angle += 360;
        return angle;
    }
}