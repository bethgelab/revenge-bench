package custom;

import robocode.*;
import robocode.util.Utils;
import java.awt.*;

public class MyTank extends AdvancedRobot {
    boolean movingForward;

    public void run() {
        setBodyColor(Color.red);
        setGunColor(Color.black);
        setRadarColor(Color.yellow);
        setBulletColor(Color.green);
        movingForward = true;
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        while (true) {
            turnRadarRight(360);
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // Basic wall avoidance
        double distToWall = Math.min(Math.min(getX(), getY()), Math.min(getBattleFieldWidth() - getX(), getBattleFieldHeight() - getY()));
        if (distToWall < 50) {
            setTurnRight(90);
        }

        // Anti-gravity: move towards center if far away
        double centerX = getBattleFieldWidth() / 2;
        double centerY = getBattleFieldHeight() / 2;
        double distToCenter = Math.hypot(getX() - centerX, getY() - centerY);
        if (distToCenter > 300) {
            double angleToCenter = Math.atan2(centerX - getX(), centerY - getY());
            setTurnRightRadians(Utils.normalRelativeAngle(angleToCenter - getHeadingRadians()));
        }

        // Movement: alternate direction
        int moveDist = 80 + (int)(Math.random() * 40);
        if (movingForward) {
            setAhead(moveDist);
        } else {
            setBack(moveDist);
        }
        movingForward = !movingForward;

        // Linear targeting
        double maxPower = getEnergy() < 50 ? 1.0 : 3.0;
        double bulletPower = Math.min(maxPower, e.getEnergy() / 4);
        double bulletSpeed = 20 - 3 * bulletPower;
        double time = e.getDistance() / bulletSpeed;
        double absBearing = e.getBearingRadians() + getHeadingRadians();
        double enemyX = getX() + Math.sin(absBearing) * e.getDistance();
        double enemyY = getY() + Math.cos(absBearing) * e.getDistance();
        double futureX = enemyX + e.getVelocity() * Math.cos(e.getHeadingRadians()) * time;
        double futureY = enemyY + e.getVelocity() * Math.sin(e.getHeadingRadians()) * time;
        double dx = futureX - getX();
        double dy = futureY - getY();
        double futureBearing = Math.atan2(dx, dy);
        double gunTurn = Utils.normalRelativeAngle(futureBearing - getGunHeadingRadians());
        setTurnGunRightRadians(gunTurn);

        if (getGunHeat() == 0 && Math.abs(gunTurn) < Math.PI / 8) {
            fire(bulletPower);
        }

        execute();
    }

    public void onHitByBullet(HitByBulletEvent e) {
        setTurnRight(90);
        setAhead(50);
    }

    public void onHitWall(HitWallEvent e) {
        setTurnRight(180);
    }
}