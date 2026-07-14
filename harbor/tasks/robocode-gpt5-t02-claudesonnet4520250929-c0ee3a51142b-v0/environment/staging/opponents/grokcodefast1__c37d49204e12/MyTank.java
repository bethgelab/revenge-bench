package custom;
import robocode.BulletHitEvent;
import robocode.BulletMissedEvent;

import robocode.Robot;
import robocode.ScannedRobotEvent;
import robocode.HitByBulletEvent;
import robocode.HitWallEvent;

import java.awt.*;

public class MyTank extends Robot {
    private double lastEnemyVelocity = 0;
    private double lastEnemyHeading = 0;
    private boolean firstScan = true;
    private double moveDirection = 1;
    private int hits = 0;
    private int misses = 0;
    private int consecutiveMisses = 0;

    public void run() {
        // Set colors for fun
        setBodyColor(Color.blue);
        setGunColor(Color.black);
        setRadarColor(Color.red);
        setBulletColor(Color.yellow);

        // Move to a corner initially with wall avoidance
        goToCorner();

        // Loop: move in circles and scan
        while (true) {
            // Move in a circle: ahead and turn body slightly
            if (getX() < 40 || getX() > getBattleFieldWidth() - 40 || getY() < 40 || getY() > getBattleFieldHeight() - 40) {
                double centerX = getBattleFieldWidth() / 2.0;
                double centerY = getBattleFieldHeight() / 2.0;
                double deltaX = centerX - getX();
                double deltaY = centerY - getY();
                double angleToCenter = Math.toDegrees(Math.atan2(deltaX, deltaY));
                double turn = angleToCenter - getHeading();
                turnRight(turn);
            }
            double aheadAmount = 40 + Math.random() * 20;
ahead(aheadAmount * moveDirection);
            double turnAmount = 5 + Math.random() * 10;
turnRight(turnAmount); // Small turn to circle
            // Turn radar right to scan
            turnRadarRight(45);
        }
    }

    private void goToCorner() {
        // Simple way to go to a corner with basic wall avoidance
        turnRight(45);
        ahead(Math.min(200, getBattleFieldWidth() - getX() - 40)); // Avoid right wall
        turnLeft(90);
        ahead(Math.min(200, getBattleFieldHeight() - getY() - 40)); // Avoid top wall
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // Stop and aim predictively
        stop();
        
        // Calculate firepower based on distance
        double dist = e.getDistance();
        double firepower = (dist < 50) ? 3 : (dist < 150) ? 2 : 1;
        firepower = Math.max(0.1, firepower + (Math.random() - 0.5) * 0.5);
        if (getEnergy() < 20 && dist > 100) firepower /= 2;
        double hitRate = (hits + misses) == 0 ? 0.5 : (double)hits / (hits + misses);
        firepower *= (hitRate > 0.7) ? 1.2 : (hitRate < 0.3) ? 0.8 : 1.0;
        if (consecutiveMisses > 2) firepower *= 0.5;
        if (e.getEnergy() < 30) firepower *= 1.5;
        else if (e.getEnergy() > 70) firepower *= 0.8;
        firepower = Math.max(0.1, Math.min(3.0, firepower));
        
        // Bullet speed
        double bulletSpeed = 20 - 3 * firepower;
        
        // Time to hit
        double time = dist / bulletSpeed;
        
        // Enemy current position relative to us
        double enemyX = getX() + dist * Math.sin(Math.toRadians(getHeading() + e.getBearing()));
        double enemyY = getY() + dist * Math.cos(Math.toRadians(getHeading() + e.getBearing()));
        
        // Predicted position
        double accel = firstScan ? 0 : (e.getVelocity() - lastEnemyVelocity);
        double accelX = accel * Math.sin(Math.toRadians(e.getHeading()));
        double accelY = accel * Math.cos(Math.toRadians(e.getHeading()));
        double futureX = enemyX + e.getVelocity() * time * Math.sin(Math.toRadians(e.getHeading()));
        double futureY = enemyY + e.getVelocity() * time * Math.cos(Math.toRadians(e.getHeading()));
        
        // Angle to predicted position
        double deltaX = futureX - getX();
        double deltaY = futureY - getY();
        double angleToTarget = Math.toDegrees(Math.atan2(deltaX, deltaY));
        
        if (getEnergy() < 10 && dist < 50) {
            double turn = angleToTarget - getHeading();
            turnRight(turn);
            ahead(dist + 20);
        } else {
        
        // Turn gun
        double gunTurn = angleToTarget - getGunHeading();
        turnGunRight(gunTurn);
        
        // Fire
        fire(firepower);
        resume();
        
        
        // Turn radar towards the enemy for locking
        double radarTurn = e.getBearing() - getRadarHeading();
        turnRadarRight(radarTurn);
        lastEnemyVelocity = e.getVelocity();
        lastEnemyHeading = e.getHeading();
        firstScan = false;
        }
    }

    public void onHitByBullet(HitByBulletEvent e) {
        // Dodge: turn perpendicular to bullet direction and move
        turnRight(90); // Turn to face perpendicular
        ahead(100); // Move away
        moveDirection = -moveDirection; // Reverse direction for next move
    }

    public void onHitWall(HitWallEvent e) {
        // Wall avoidance: turn away and move
        turnRight(180); // Turn around
        ahead(100); // Move away from wall
    }

    public void onBulletHit(BulletHitEvent e) {
        hits++;
        consecutiveMisses = 0;
    }

    public void onBulletMissed(BulletMissedEvent e) {
        misses++;
        consecutiveMisses++;
    }
}