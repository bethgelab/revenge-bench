package custom;

import robocode.Robot;
import robocode.ScannedRobotEvent;
import robocode.HitByBulletEvent;
import robocode.HitWallEvent;
import java.awt.*;

public class MyTank extends Robot {
    double enemyX = 0, enemyY = 0;
    double velX = 0, velY = 0;
    double prevActualX = 0, prevActualY = 0;
    long prevTime = 0;
    
    public void run() {
        setBodyColor(Color.red);
        setGunColor(Color.black);
        setRadarColor(Color.yellow);
        setBulletColor(Color.green);
        setScanColor(Color.green);
        
        while(true) {
            boolean oneOnOne = (getOthers() == 1);
            // Wall avoidance
            double margin = 50;
            if (getX() < margin || getX() > getBattleFieldWidth() - margin ||
                getY() < margin || getY() > getBattleFieldHeight() - margin) {
                turnRight(90);
            }
            double distToEnemy = Math.hypot(enemyX - getX(), enemyY - getY());
            
            // Flee if low energy
            if (getEnergy() < 20) {
                double angleAway = Math.toDegrees(Math.atan2(getX() - enemyX, getY() - enemyY));
                turnRight(angleAway - getHeading());
                ahead(100);
            } else if (distToEnemy < 50) {
                // Ramming: face enemy and charge
                double angleToEnemy = Math.toDegrees(Math.atan2(enemyX - getX(), enemyY - getY()));
                turnRight(angleToEnemy - getHeading());
                ahead(100);
            } else if (distToEnemy < 200) {
                // Circling
                double angleToEnemy = Math.toDegrees(Math.atan2(enemyX - getX(), enemyY - getY()));
                turnRight(angleToEnemy - getHeading());
                ahead(oneOnOne ? 75 : 50);
                turnRight(90);
            } else {
                // Approaching
                double angleToEnemy = Math.toDegrees(Math.atan2(enemyX - getX(), enemyY - getY()));
                turnRight(angleToEnemy - getHeading());
                ahead(oneOnOne ? 150 : 100);
            }
            turnRadarRight(360);
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        double distance = e.getDistance();
        double power = Math.min(3, Math.min(400 / distance, getEnergy() - 0.1));
        // Lock radar
        turnRadarRight(getHeading() - getRadarHeading() + e.getBearing());
        // Calculate current enemy position
        double enemyBearing = getHeading() + e.getBearing();
        double actualX = getX() + Math.sin(Math.toRadians(enemyBearing)) * distance;
        double actualY = getY() + Math.cos(Math.toRadians(enemyBearing)) * distance;
        // Calculate velocity from position changes
        long currentTime = getTime();
        if (prevTime > 0) {
            double timeDiff = currentTime - prevTime;
            this.velX = (actualX - prevActualX) / timeDiff;
            this.velY = (actualY - prevActualY) / timeDiff;
        }
        prevActualX = actualX;
        prevActualY = actualY;
        prevTime = currentTime;
        // Predictive firing using tracked velocity if available, else event
        double predVelX = (prevTime == 0) ? Math.sin(Math.toRadians(e.getHeading())) * e.getVelocity() : this.velX;
        double predVelY = (prevTime == 0) ? Math.cos(Math.toRadians(e.getHeading())) * e.getVelocity() : this.velY;
        double bulletSpeed = 20 - 3 * power;
        double time = distance / bulletSpeed;
        enemyX = actualX + predVelX * time;
        enemyY = actualY + predVelY * time;
        this.enemyX = enemyX;
        this.enemyY = enemyY;
        double absBearing = Math.toDegrees(Math.atan2(enemyX - getX(), enemyY - getY()));
        turnGunRight(absBearing - getGunHeading());
        fire(power);
    }
    
    public void onHitByBullet(HitByBulletEvent e) {
        turnRight(90);
        ahead(100);
    }
    
    public void onHitWall(HitWallEvent e) {
        back(50);
        turnRight(90);
    }
}