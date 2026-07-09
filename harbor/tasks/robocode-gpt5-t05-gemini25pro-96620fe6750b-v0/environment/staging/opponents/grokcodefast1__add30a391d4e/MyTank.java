package custom;

import robocode.Robot;
import robocode.ScannedRobotEvent;
import robocode.HitWallEvent;

import java.awt.*;

public class MyTank extends Robot {
    private double prevEnemyHeading = 0;
    private double enemyX, enemyY;
    private long prevScanTime = 0;
    private double enemyBearing, enemyDistance, enemyVelocity, enemyHeading;
    private long lastScanTime;

    public void run() {
        setColors(Color.red, Color.blue, Color.green);
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        while(true) {
            ahead(100);
            turnRight(20);
            turnRadarRight(45);
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        enemyBearing = e.getBearing();
        enemyDistance = e.getDistance();
        enemyVelocity = e.getVelocity();
        enemyHeading = e.getHeading();
        double absoluteBearingRad = Math.toRadians(getHeading() + enemyBearing);
        enemyX = getX() + Math.sin(absoluteBearingRad) * enemyDistance;
        enemyY = getY() + Math.cos(absoluteBearingRad) * enemyDistance;
        lastScanTime = getTime();
        double turnRate = 0;
        if (prevScanTime != 0) {
            double timeDiff = lastScanTime - prevScanTime;
            if (timeDiff > 0) {
                turnRate = Math.toRadians(enemyHeading - prevEnemyHeading) / timeDiff;
            }
        }
        double distance = e.getDistance();
        double power = Math.min(3.0, 400 / distance);
        double bulletSpeed = 20 - 3 * power;
        double predictedTime = enemyDistance / bulletSpeed;
        // linear prediction
        double predX = enemyX + enemyVelocity * predictedTime * Math.sin(Math.toRadians(enemyHeading));
        double predY = enemyY + enemyVelocity * predictedTime * Math.cos(Math.toRadians(enemyHeading));
        double predBearing = Math.atan2(predX - getX(), predY - getY()) - Math.toRadians(getGunHeading());
        turnGunRight(Math.toDegrees(predBearing));
        fire(power);
        turnRadarRight(enemyBearing - getRadarHeading() + 45);
        prevEnemyHeading = enemyHeading;
        prevScanTime = lastScanTime;
    }

    public void onHitWall(HitWallEvent e) {
        turnRight(90);
        back(50);
    }
}