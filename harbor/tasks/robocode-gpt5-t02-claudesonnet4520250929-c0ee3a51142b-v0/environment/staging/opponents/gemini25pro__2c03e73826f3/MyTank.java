package custom;

import robocode.*;
import java.awt.Color;
import java.awt.geom.Point2D;

public class MyTank extends AdvancedRobot {

    private int moveDirection = 1; // 1 for forward, -1 for backward
    private double enemyLastHeading = 0.0;
    private long enemyLastScanTime = 0;
    private double enemyLastTurnRate = 0.0;

    public void run() {
        setBodyColor(Color.blue);
        setGunColor(Color.blue);
        setRadarColor(Color.black);
        setAdjustGunForRobotTurn(true);
        while (true) {
            setTurnRadarRight(Double.POSITIVE_INFINITY);
            execute();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        doRadar(e);
        doMovement(e);
        doGunAndFire(e);
        execute();
    }
    
    private void doRadar(ScannedRobotEvent e) {
        double absoluteBearing = getHeading() + e.getBearing();
        double radarTurnAngle = robocode.util.Utils.normalRelativeAngleDegrees(absoluteBearing - getRadarHeading());
        setTurnRadarRight(radarTurnAngle * 2.0);
    }
    
    private void doMovement(ScannedRobotEvent e) {
        double moveAmount = 150;
        double wallMargin = 60.0;
        double futureX = getX() + (moveAmount * moveDirection) * Math.sin(Math.toRadians(getHeading()));
        double futureY = getY() + (moveAmount * moveDirection) * Math.cos(Math.toRadians(getHeading()));

        if (futureX < wallMargin || futureX > getBattleFieldWidth() - wallMargin ||
            futureY < wallMargin || futureY > getBattleFieldHeight() - wallMargin) {
            moveDirection *= -1;
        }
        
        double turnOffset = 90;
        if (e.getDistance() < 200) {
            moveDirection = -1;
            turnOffset = 100;
        } else if (e.getDistance() > 400) {
            turnOffset = 80;
        }

        setTurnRight(e.getBearing() + turnOffset - (15 * moveDirection * Math.random()));
        setAhead((moveAmount + (Math.random() * 40)) * moveDirection);
    }

    private void doGunAndFire(ScannedRobotEvent e) {
        double firePower = Math.min(400 / e.getDistance(), 3); 
        if (getEnergy() < 25) {
            firePower = Math.min(firePower, 1.5);
        }
        if (e.getVelocity() == 0 && getEnergy() > 50) {
            firePower = 3.0;
        }

        Point2D.Double predictedPosition = predictEnemyPosition(e, firePower);
        
        double theta = robocode.util.Utils.normalAbsoluteAngle(Math.atan2(predictedPosition.getX() - getX(), predictedPosition.getY() - getY()));
        setTurnGunRightRadians(robocode.util.Utils.normalRelativeAngle(theta - getGunHeadingRadians()));
        
        if (getGunHeat() == 0 && Math.abs(getGunTurnRemaining()) < 10 && getEnergy() > firePower) {
            fire(firePower);
        }
    }

    private Point2D.Double predictEnemyPosition(ScannedRobotEvent e, double firePower) {
        double bulletSpeed = 20 - firePower * 3;
        double absoluteBearing = getHeadingRadians() + e.getBearingRadians();
        double enemyX = getX() + e.getDistance() * Math.sin(absoluteBearing);
        double enemyY = getY() + e.getDistance() * Math.cos(absoluteBearing);
        double enemyHeading = e.getHeadingRadians();
        double enemyVelocity = e.getVelocity();
        long timeDiff = getTime() - enemyLastScanTime;
        double enemyTurnRate; if (timeDiff > 0) { enemyTurnRate = robocode.util.Utils.normalRelativeAngle(e.getHeadingRadians() - enemyLastHeading) / timeDiff; enemyLastTurnRate = enemyTurnRate; } else { enemyTurnRate = enemyLastTurnRate; }
        enemyLastHeading = e.getHeadingRadians();
        enemyLastScanTime = getTime();

        double deltaTime = 0;
        double battleFieldHeight = getBattleFieldHeight(), battleFieldWidth = getBattleFieldWidth();
        double predictedX = enemyX, predictedY = enemyY;
        
        double predictedHeading = enemyHeading;
        while((++deltaTime) * bulletSpeed < java.awt.geom.Point2D.distance(getX(), getY(), predictedX, predictedY)){
            predictedHeading += enemyTurnRate;
            predictedX += Math.sin(predictedHeading) * enemyVelocity;
            predictedY += Math.cos(predictedHeading) * enemyVelocity;
            if( predictedX < 18.0 || predictedY < 18.0 || predictedX > battleFieldWidth - 18.0 || predictedY > battleFieldHeight - 18.0){
                predictedX = Math.min(Math.max(18.0, predictedX), battleFieldWidth - 18.0);
                predictedY = Math.min(Math.max(18.0, predictedY), battleFieldHeight - 18.0);
                break;
            }
        }
        return new Point2D.Double(predictedX, predictedY);
    }

    public void onHitByBullet(HitByBulletEvent e) {
        // The enemy has a good lock on our movement pattern. The most disruptive
        // response is to reverse our direction of circling to break their prediction.
        moveDirection *= -1;
    }
    
    public void onHitWall(HitWallEvent e) {
        moveDirection *= -1;
        setTurnRight(45 - 90 * Math.random());
        setAhead(150 * moveDirection);
        execute();
    }
}