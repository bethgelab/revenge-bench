package custom;

import robocode.*;
import robocode.util.Utils;
import java.awt.Color;

public class MyTank extends AdvancedRobot {
    private int moveDirection = 1;
    private double enemyEnergy = 100.0;
    private int movementCounter = 0;
    
    public void run() {
        // Set colors
        setBodyColor(Color.blue);
        setGunColor(Color.black);
        setRadarColor(Color.yellow);
        
        // Independent movement of gun and radar
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        
        while (true) {
            // Continuous radar sweep
            setTurnRadarRight(360);
            
            // Semi-random movement pattern to avoid being predictable
            movementCounter++;
            if (movementCounter % 20 == 0) {
                // Occasionally change direction randomly
                if (Math.random() < 0.3) {
                    moveDirection *= -1;
                }
            }
            
            // Oscillating movement pattern with slight randomization
            double moveDistance = 120 + Math.random() * 60; // 120-180 instead of fixed 150
            setAhead(moveDistance * moveDirection);
            
            execute();
        }
    }
    
    public void onScannedRobot(ScannedRobotEvent e) {
        // Enhanced energy-based power calculation
        double firePower;
        if (getEnergy() > 60) {
            firePower = Math.min(3.0, getEnergy() / 3);
        } else if (getEnergy() > 30) {
            firePower = Math.min(2.5, getEnergy() / 4);
        } else {
            firePower = Math.min(1.5, getEnergy() / 6);
        }
        
        // Predictive targeting with enhanced prediction
        double absoluteBearing = getHeadingRadians() + e.getBearingRadians();
        double enemyX = getX() + e.getDistance() * Math.sin(absoluteBearing);
        double enemyY = getY() + e.getDistance() * Math.cos(absoluteBearing);
        double enemyHeading = e.getHeadingRadians();
        double enemyVelocity = e.getVelocity();
        
        // Improved linear prediction with convergence check
        double deltaTime = 0;
        double predictedX = enemyX;
        double predictedY = enemyY;
        double bulletPower = firePower;
        double bulletSpeed = 20 - 3 * bulletPower;
        
        // Iterate to find intercept point with convergence check
        double lastDeltaTime = 0;
        for (int i = 0; i < 20; i++) {
            deltaTime = Math.sqrt(Math.pow(predictedX - getX(), 2) + Math.pow(predictedY - getY(), 2)) / bulletSpeed;
            predictedX = enemyX + Math.sin(enemyHeading) * enemyVelocity * deltaTime;
            predictedY = enemyY + Math.cos(enemyHeading) * enemyVelocity * deltaTime;
            
            // Check for convergence - if deltaTime isn't changing much, we're done
            if (Math.abs(deltaTime - lastDeltaTime) < 0.01) {
                break;
            }
            lastDeltaTime = deltaTime;
        }
        
        // Calculate angle to predicted position
        double theta = Utils.normalAbsoluteAngle(Math.atan2(predictedX - getX(), predictedY - getY()));
        
        // Turn gun to target
        setTurnGunRightRadians(Utils.normalRelativeAngle(theta - getGunHeadingRadians()));
        
        // Fire if gun is aimed well (slightly relaxed threshold for more shots)
        if (Math.abs(getGunTurnRemaining()) < 15) {
            setFire(firePower);
        }
        
        // Narrow radar lock on target
        double radarTurn = getHeadingRadians() + e.getBearingRadians() - getRadarHeadingRadians();
        setTurnRadarRightRadians(Utils.normalRelativeAngle(radarTurn));
        
        // Energy drop detection for dodging
        if (enemyEnergy > e.getEnergy()) {
            // Enemy fired, change direction with some randomization
            moveDirection *= -1;
            double dodgeDistance = 120 + Math.random() * 80; // 120-200
            setAhead(dodgeDistance * moveDirection);
            
            // Occasionally add a turn for more unpredictable dodging
            if (Math.random() < 0.4) {
                setTurnRight((Math.random() - 0.5) * 60); // -30 to +30 degrees
            }
        }
        enemyEnergy = e.getEnergy();
    }
    
    public void onHitByBullet(HitByBulletEvent e) {
        // Enhanced perpendicular movement when hit
        moveDirection *= -1;
        double turnAngle = 90 - e.getBearing() + (Math.random() - 0.5) * 30; // Add some randomness
        setTurnRight(turnAngle);
        double moveDistance = 120 + Math.random() * 80;
        setAhead(moveDistance * moveDirection);
    }
    
    public void onHitWall(HitWallEvent e) {
        // Reverse direction when hitting wall with slight randomization
        moveDirection *= -1;
        double moveDistance = 120 + Math.random() * 60;
        setAhead(moveDistance * moveDirection);
        
        // Add a small turn to avoid getting stuck in corners
        setTurnRight((Math.random() - 0.5) * 40);
    }
    
    public void onHitRobot(HitRobotEvent e) {
        // If we hit a robot, back up and fire
        if (e.isMyFault()) {
            setTurnRight(10 + Math.random() * 20); // 10-30 degrees
            setBack(20 + Math.random() * 20); // 20-40 distance
            setFire(3);
        }
    }
}