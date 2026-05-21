package custom;

import robocode.*;
import robocode.util.Utils;
import java.awt.Color;

public class MyTank extends AdvancedRobot {
    boolean movingForward;

    public void run() {
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);
        setBodyColor(Color.red);
        setGunColor(Color.black);
        setRadarColor(Color.yellow);
        setBulletColor(Color.green);
        setScanColor(Color.green);
        movingForward = true;

        setTurnRadarRight(Double.POSITIVE_INFINITY);

        while (true) {
            execute();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        double radarTurn = getHeading() - getRadarHeading() + e.getBearing();
        setTurnRadarRight(Utils.normalRelativeAngleDegrees(radarTurn) * 1.2);

        double absoluteBearing = getHeading() + e.getBearing();
        double bearingFromGun = Utils.normalRelativeAngleDegrees(absoluteBearing - getGunHeading());

        setTurnGunRight(bearingFromGun);

        if (Math.abs(bearingFromGun) <= 3 && getGunHeat() == 0) {
            double firePower = Math.min(400 / e.getDistance(), 3);
            fire(firePower);
        }
        
        if (movingForward) {
            setAhead(100);
        } else {
            setBack(100);
        }
        setTurnRight(e.getBearing() + 90);
    }
    
    public void reverseDirection() {
        movingForward = !movingForward;
    }

    public void onHitWall(HitWallEvent e) {
        reverseDirection();
    }

    public void onHitRobot(HitRobotEvent e) {
        if (e.isMyFault()) {
            reverseDirection();
        }
    }
}